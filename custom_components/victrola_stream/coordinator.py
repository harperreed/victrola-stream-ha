# ABOUTME: Push-first coordinator for the Victrola Stream and its VictrolaState.
# ABOUTME: Full reads at start and every 5 minutes; device events update it in between.
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKOFF_MAX_S,
    BACKOFF_START_S,
    DOMAIN,
    FULL_REFRESH_INTERVAL,
    IDENTITY_PATHS,
    OUTPUT_TOGGLES,
    POLL_TIMEOUT_S,
    SPEAKERS_PATH,
    STATE_PATHS,
    SUBSCRIBED_PATHS,
    TRACKED_PATHS,
    URL_PATHS,
)
from .nsdk import (
    EMPTY,
    NsdkClient,
    NsdkConnectionError,
    NsdkError,
    NsdkEvent,
    NsdkInvalidPath,
    NsdkRow,
    NsdkValue,
)

_LOGGER = logging.getLogger(__name__)

_OUTPUT_TOGGLE_PATHS = frozenset(OUTPUT_TOGGLES.values())

type VictrolaConfigEntry = ConfigEntry[VictrolaCoordinator]


@dataclass(frozen=True, slots=True)
class Speaker:
    """One speaker row the turntable can stream to; `preferred` marks the default."""

    id: str
    type: str
    title: str
    preferred: bool


def _speakers_from_rows(rows: Iterable[NsdkRow]) -> tuple[Speaker, ...]:
    """Keep the rows that name a speaker; headers and output toggles have no id."""
    return tuple(
        Speaker(
            id=row.id, type=row.type or "", title=row.title, preferred=row.preferred
        )
        for row in rows
        if row.id
    )


@dataclass(frozen=True, slots=True)
class VictrolaState:
    """One snapshot of the device. Entities read only this."""

    values: Mapping[str, NsdkValue]
    missing: frozenset[str]  # paths that answered invalidPath at the last full read
    speakers: tuple[Speaker, ...]

    def value(self, path: str) -> NsdkValue:
        return self.values.get(path, EMPTY)

    @property
    def output(self) -> str | None:
        """The OUTPUT_TOGGLES key whose node reads True, or None if none does."""
        return next(
            (
                key
                for key, path in OUTPUT_TOGGLES.items()
                if self.value(path).as_bool() is True
            ),
            None,
        )

    def stream_url(self, fmt: str) -> str | None:
        """The stream URL for a URL_PATHS key; None while the device reports none."""
        return self.value(URL_PATHS[fmt]).as_str() or None

    def with_value(self, path: str, value: NsdkValue) -> VictrolaState:
        return replace(self, values={**self.values, path: value})

    def with_speakers(self, speakers: Iterable[Speaker]) -> VictrolaState:
        return replace(self, speakers=tuple(speakers))


class VictrolaCoordinator(DataUpdateCoordinator[VictrolaState]):
    """Keeps the one VictrolaState current: full reads plus the device's events."""

    config_entry: VictrolaConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: VictrolaConfigEntry, client: NsdkClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=FULL_REFRESH_INTERVAL,
        )
        self.client = client
        self._queue_id: str | None = None
        self._push_task: asyncio.Task[None] | None = None

    async def _async_update_data(self) -> VictrolaState:
        """Read every identity and state node, plus the speaker list."""
        try:
            values, missing = await self.client.read_nodes(IDENTITY_PATHS + STATE_PATHS)
            try:
                speakers = await self._read_speakers()
            except NsdkInvalidPath:  # this device has no speaker list
                speakers, missing = (), missing | {SPEAKERS_PATH}
        except (NsdkError, NsdkConnectionError) as err:
            raise UpdateFailed(f"Error reading {self.client.host}: {err!r}") from err
        return VictrolaState(values=values, missing=missing, speakers=speakers)

    @callback
    def async_start_push(self) -> None:
        """Start the push loop as a background task tied to the config entry."""
        self._push_task = self.config_entry.async_create_background_task(
            self.hass, self._push_loop(), name=f"{DOMAIN} push loop"
        )

    async def async_stop_push(self) -> None:
        """Cancel the push loop, then drop its event queue (best effort)."""
        if self._push_task is not None:
            self._push_task.cancel()
            # wait() doesn't raise the loop's CancelledError at us, yet a
            # cancellation of our own caller still propagates.
            await asyncio.wait([self._push_task])
            self._push_task = None
        await self._async_drop_queue()

    async def async_shutdown(self) -> None:
        """Stop the push loop and unsubscribe, then let the base class finish up.

        Idempotent: async_stop_push already tolerates a second call, and the
        base class guards its own teardown the same way.
        """
        await self.async_stop_push()
        await super().async_shutdown()

    async def async_write(self, path: str, value: NsdkValue) -> None:
        """Write a typed value; the snapshot takes the device's read-back."""
        readback = await self.client.set_typed(path, value)
        self._async_publish(self.data.with_value(path, readback))
        if path in _OUTPUT_TOGGLE_PATHS:
            await self._async_reread_speakers()

    async def async_activate(
        self, path: str, value: Any, *, reread_speakers: bool = False
    ) -> None:
        """Fire an action node, then re-read the speaker list if asked."""
        await self.client.activate(path, value)
        if reread_speakers:
            await self._async_reread_speakers()

    async def _push_loop(self) -> None:
        """Fold device events into the snapshot as they arrive; reconnect on failure.

        Every pass subscribes, then does a full read, then polls. A change made
        before the subscribe shows up in that read, and one made after it
        arrives as an event; on the first pass that covers the gap after
        setup's own read. What sends no event, such as the speaker list, waits
        for the 5-minute read.
        """
        backoff = BACKOFF_START_S
        while True:
            try:
                queue = await self.client.subscribe(SUBSCRIBED_PATHS)
                self._queue_id = queue
                # Read everything, stream URLs included: the device may have
                # rebooted, or changed since the last read.
                await self.async_refresh()
                if not self.last_update_success:
                    # async_refresh logs and swallows a failed read. Polling
                    # on would let the next event mark the old snapshot, with
                    # its old stream ports, current again; retry instead.
                    raise NsdkConnectionError(
                        f"full read after subscribing failed: {self.last_exception}"
                    )
                backoff = BACKOFF_START_S
                while True:
                    events = await self.client.poll(queue, POLL_TIMEOUT_S)
                    if events:
                        await self._apply(events)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # any failure, expected or not, retries
                if isinstance(err, (NsdkError, NsdkConnectionError)):
                    _LOGGER.debug(
                        "Push loop failed (%s); retrying in %s s", err, backoff
                    )
                else:
                    # A bug, or an error the client failed to map. Say so loudly,
                    # but don't let it end the loop and leave entities available.
                    _LOGGER.exception(
                        "Push loop failed unexpectedly; retrying in %s s", backoff
                    )
                # Entities go unavailable now, not at the next full read.
                self.async_set_update_error(err)
                await self._async_drop_queue()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)

    async def _async_drop_queue(self) -> None:
        """Unsubscribe the event queue the loop holds, if any, then forget it.

        Best effort: it swallows every error, since the device may be gone and
        cleanup must not end the push loop. A cancel still propagates and
        leaves the id in place, so async_stop_push tries again.
        """
        queue_id = self._queue_id
        if queue_id is None:
            return
        try:
            await self.client.unsubscribe(queue_id, SUBSCRIBED_PATHS)
        except Exception as err:  # best effort: see the docstring
            _LOGGER.debug("Could not unsubscribe event queue %s: %s", queue_id, err)
        self._queue_id = None

    async def _apply(self, events: list[NsdkEvent]) -> None:
        """Fold tracked events into a copy of the snapshot.

        An output-toggle event, with or without a value, re-reads the speaker
        list: the device shows Sonos groups only in Sonos mode.
        """
        state = self.data
        reread_speakers = False
        for event in events:
            if event.path not in TRACKED_PATHS:
                continue
            if event.path in _OUTPUT_TOGGLE_PATHS:
                reread_speakers = True
            if event.value is not None:
                state = state.with_value(event.path, event.value)
        if state is not self.data:
            self._async_publish(state)
        if reread_speakers:
            await self._async_reread_speakers()

    async def _read_speakers(self) -> tuple[Speaker, ...]:
        return _speakers_from_rows(await self.client.get_rows(SPEAKERS_PATH))

    async def _async_reread_speakers(self) -> None:
        if SPEAKERS_PATH in self.data.missing:
            return  # this device has no speaker list; the next full read checks again
        speakers = await self._read_speakers()
        # Take self.data only now: events may have changed it during the read.
        self._async_publish(self.data.with_speakers(speakers))

    @callback
    def _async_publish(self, state: VictrolaState) -> None:
        """Set the snapshot and notify listeners; leave the full-read timer alone.

        async_set_updated_data would push the 5-minute full read back on every
        call, so steady events (Wi-Fi RSSI, say) would postpone it forever, and
        changes that send no event, like the speaker list, would go unseen.
        """
        self.data = state
        self.last_update_success = True  # as async_set_updated_data would set it
        self.async_update_listeners()
