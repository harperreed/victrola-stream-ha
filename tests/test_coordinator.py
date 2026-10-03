# ABOUTME: Tests for VictrolaCoordinator: full reads, the push loop, confirmed writes.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import asyncio
import copy
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_KNOB_BRIGHTNESS,
    NODE_MOTOR,
    NODE_RCA_DELAY,
    NODE_SERIAL,
    NODE_SET_DEFAULT_OUTPUT,
    NODE_VOLUME,
    OUTPUT_TOGGLES,
    SPEAKERS_PATH,
    SUBSCRIBED_PATHS,
    URL_PATHS,
)
from custom_components.victrola_stream.coordinator import VictrolaCoordinator
from custom_components.victrola_stream.nsdk import (
    NsdkEvent,
    NsdkValue,
    NsdkWriteRejected,
)
from tests.conftest import wait_for
from tests.fake_device import FakeVictrola

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_COORDINATOR_MODULE = "custom_components.victrola_stream.coordinator"
# The documented URL shape (victrola-stream-go docs/live-stream-discovery.md).
# The recorded device sat in network standby, so its own URLs read "".
_FLAC_URL = "http://192.0.2.10:44323/stream.flac"
_FLAC_URL_AFTER_REBOOT = "http://192.0.2.10:40000/stream.flac"


@pytest.fixture
async def coordinator(hass, client, fake, monkeypatch):
    monkeypatch.setattr(f"{_COORDINATOR_MODULE}.BACKOFF_START_S", 0.01)
    monkeypatch.setattr(f"{_COORDINATOR_MODULE}.POLL_TIMEOUT_S", 1)
    fake.poll_wait_s = 0.01
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: fake.host},
        unique_id=fake.values[NODE_SERIAL][0]["string_"],
    )
    entry.add_to_hass(hass)
    coordinator = VictrolaCoordinator(hass, entry, client)
    try:
        yield coordinator
    finally:
        await coordinator.async_stop_push()
        await coordinator.async_shutdown()  # cancels a scheduled full read


async def _start_push(coordinator: VictrolaCoordinator, fake: FakeVictrola) -> None:
    """Do the first full read, start the push loop, and wait until it subscribes."""
    await coordinator.async_refresh()
    coordinator.async_start_push()
    await wait_for(lambda: fake.subscribe_calls)


def _string_value(text: str) -> list[dict[str, Any]]:
    return [{"type": "string_", "string_": text}]


def _recorded_event(path: str) -> dict[str, Any]:
    batches = json.loads((_FIXTURES_DIR / "events.json").read_text())
    return next(event for batch in batches for event in batch if event["path"] == path)


def _speaker_list_without_speakers(fake: FakeVictrola) -> dict[str, Any]:
    """The recorded speaker list minus its Sonos rows, as outside Sonos mode."""
    body = copy.deepcopy(fake.rows[SPEAKERS_PATH])
    body["rows"] = [row for row in body["rows"] if "id" not in row]
    body["rowsCount"] = len(body["rows"])
    return body


def _get_data_calls(aioclient_mock, path: str) -> int:
    return sum(
        1
        for _method, url, _data, _headers in aioclient_mock.mock_calls
        if url.path == "/api/getData" and url.query.get("path") == path
    )


def _polled_queue_ids(aioclient_mock) -> set[str]:
    return {
        url.query["queueId"]
        for _method, url, _data, _headers in aioclient_mock.mock_calls
        if url.path == "/api/event/pollQueue"
    }


def _coordinator_errors(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == _COORDINATOR_MODULE and record.levelno >= logging.ERROR
    ]


# HA logs an outage once, on the way down, however many retries follow.
_OFFLINE_ERROR = (
    "Error requesting victrola_stream data: victrola stream device is offline"
)


async def test_full_read_builds_snapshot(coordinator, fake):
    fake.values[URL_PATHS["flac"]] = _string_value(_FLAC_URL)

    await coordinator.async_refresh()

    data = coordinator.data
    assert data.output == "sonos"
    assert len([speaker for speaker in data.speakers if speaker.preferred]) == 1
    # Header, description and output-toggle rows carry no id and are skipped.
    assert {speaker.type for speaker in data.speakers} == {"victrolaOutputSonos"}
    assert data.stream_url("flac").endswith("/stream.flac")
    assert data.stream_url("mp3") is None  # the recorded empty string


async def test_full_read_records_missing_paths(coordinator, fake):
    del fake.values[NODE_RCA_DELAY]

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert NODE_RCA_DELAY in coordinator.data.missing
    assert coordinator.data.value(NODE_RCA_DELAY).is_empty


async def test_empty_value_reads_as_empty(coordinator, fake):
    fake.values[NODE_MOTOR] = [{}]

    await coordinator.async_refresh()

    assert coordinator.data.value(NODE_MOTOR).is_empty
    assert NODE_MOTOR not in coordinator.data.missing


async def test_full_read_failure_raises_update_failed(coordinator, fake):
    fake.offline = True

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_missing_speaker_list_reads_as_no_speakers(coordinator, fake):
    del fake.rows[SPEAKERS_PATH]  # the fake answers its recorded invalidPath body

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.speakers == ()
    assert SPEAKERS_PATH in coordinator.data.missing

    # An output change doesn't try to re-read a list the device lacks.
    await coordinator.async_write(OUTPUT_TOGGLES["sonos"], NsdkValue.of_bool(False))

    assert coordinator.data.value(OUTPUT_TOGGLES["sonos"]).as_bool() is False


async def test_events_do_not_postpone_the_full_read(
    hass, coordinator, fake, freezer, monkeypatch
):
    # The test loop runs in debug mode, which times each task step by the
    # frozen clock, so every tick below would log a bogus slow-step warning.
    monkeypatch.setattr(hass.loop, "slow_callback_duration", 3600)
    await coordinator.async_refresh()
    coordinator.async_add_listener(lambda: None)  # HA only schedules for listeners
    # A Sonos group drops off. No event says so; only a full read can see it.
    gone = coordinator.data.speakers[0]
    body = copy.deepcopy(fake.rows[SPEAKERS_PATH])
    body["rows"] = [row for row in body["rows"] if row.get("id") != gone.id]
    body["rowsCount"] = len(body["rows"])
    fake.rows[SPEAKERS_PATH] = body
    event = NsdkEvent.from_json(_recorded_event(NODE_VOLUME))

    for _ in range(4):  # an event every minute, well inside the 5-minute interval
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await coordinator._apply([event])

    assert gone in coordinator.data.speakers  # 4 minutes: no full read due yet

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert gone not in coordinator.data.speakers


async def test_push_applies_event(coordinator, fake):
    # The fixture records the platter at rest; this recorded event starts it.
    event = _recorded_event(NODE_MOTOR)
    await _start_push(coordinator, fake)
    assert coordinator.data.value(NODE_MOTOR).as_bool() is False

    fake.push_event(event["path"], event["itemValue"])

    await wait_for(lambda: coordinator.data.value(NODE_MOTOR).as_bool() is True)


async def test_malformed_event_does_not_stop_the_push_loop(coordinator, fake, caplog):
    event = _recorded_event(NODE_MOTOR)
    await _start_push(coordinator, fake)

    # An itemValue that is a bare string, not a typed value; then a real event.
    fake.push_raw_event({**event, "itemValue": "garbage"})
    fake.push_event(event["path"], event["itemValue"])

    await wait_for(lambda: coordinator.data.value(NODE_MOTOR).as_bool() is True)
    assert _coordinator_errors(caplog) == []


async def test_output_toggle_event_rereads_speakers(coordinator, fake):
    await _start_push(coordinator, fake)
    assert coordinator.data.speakers
    fake.rows[SPEAKERS_PATH] = _speaker_list_without_speakers(fake)

    fake.push_event(OUTPUT_TOGGLES["sonos"], {"type": "bool_", "bool_": False})

    await wait_for(lambda: coordinator.data.speakers == ())
    assert coordinator.data.output is None


async def test_apply_ignores_untracked_and_valueless_events(coordinator, fake):
    await coordinator.async_refresh()
    before = coordinator.data

    await coordinator._apply(
        [
            NsdkEvent(
                "settings:/victrola/notTracked", "update", NsdkValue.of_bool(True)
            ),
            NsdkEvent(NODE_MOTOR, "update", None),
        ]
    )

    assert coordinator.data is before

    # A valueless output-toggle event still means the speaker list may differ.
    fake.rows[SPEAKERS_PATH] = _speaker_list_without_speakers(fake)
    await coordinator._apply([NsdkEvent(OUTPUT_TOGGLES["sonos"], "update", None)])

    assert coordinator.data.speakers == ()
    assert coordinator.data.values == before.values


async def test_reconnect_rereads_urls(coordinator, fake, caplog):
    await _start_push(coordinator, fake)

    fake.offline = True
    await wait_for(lambda: not coordinator.last_update_success)
    fake.values[URL_PATHS["flac"]] = _string_value(_FLAC_URL_AFTER_REBOOT)
    fake.drop_queues()
    fake.offline = False

    await wait_for(
        lambda: (
            coordinator.last_update_success
            and coordinator.data.stream_url("flac") == _FLAC_URL_AFTER_REBOOT
        )
    )
    assert _coordinator_errors(caplog) == [_OFFLINE_ERROR]


async def test_reconnect_retries_a_failed_full_read(
    coordinator, fake, aioclient_mock, caplog
):
    await _start_push(coordinator, fake)
    fake.offline = True
    await wait_for(lambda: not coordinator.last_update_success)

    # The device answers again with new stream ports, but one read still fails.
    fake.values[URL_PATHS["flac"]] = _string_value(_FLAC_URL_AFTER_REBOOT)
    fake.raw_replies[NODE_MOTOR] = "not json"
    motor_reads = _get_data_calls(aioclient_mock, NODE_MOTOR)
    fake.drop_queues()
    fake.offline = False
    await wait_for(lambda: _get_data_calls(aioclient_mock, NODE_MOTOR) > motor_reads)
    del fake.raw_replies[NODE_MOTOR]

    await wait_for(
        lambda: (
            coordinator.last_update_success
            and coordinator.data.stream_url("flac") == _FLAC_URL_AFTER_REBOOT
        )
    )
    assert _coordinator_errors(caplog) == [_OFFLINE_ERROR]


async def test_push_loop_survives_an_unexpected_error(
    coordinator, fake, aioclient_mock, caplog
):
    await _start_push(coordinator, fake)
    await wait_for(lambda: _polled_queue_ids(aioclient_mock))
    availability: list[bool] = []
    coordinator.async_add_listener(
        lambda: availability.append(coordinator.last_update_success)
    )

    # Not a device reply: aiohttp raises this once its session is closed.
    fake.poll_fault = RuntimeError("Session is closed")

    # The loop logs it, subscribes again, and takes events on the new queue.
    await wait_for(lambda: len(_polled_queue_ids(aioclient_mock)) == 2)
    event = _recorded_event(NODE_MOTOR)
    fake.push_event(event["path"], event["itemValue"])
    await wait_for(lambda: coordinator.data.value(NODE_MOTOR).as_bool() is True)

    assert False in availability  # its entities went unavailable meanwhile
    assert coordinator.last_update_success
    (logged,) = [
        record
        for record in caplog.records
        if record.name == _COORDINATOR_MODULE
        and record.levelno >= logging.ERROR
        and record.exc_info
    ]
    assert isinstance(logged.exc_info[1], RuntimeError)


async def test_async_write_updates_snapshot_from_readback(coordinator, fake):
    await coordinator.async_refresh()

    await coordinator.async_write(NODE_KNOB_BRIGHTNESS, NsdkValue.of_int(3))

    assert coordinator.data.value(NODE_KNOB_BRIGHTNESS) == NsdkValue("i32_", 3)
    assert fake.set_calls == [
        {
            "path": NODE_KNOB_BRIGHTNESS,
            "role": "value",
            "value": {"type": "i32_", "i32_": 3},
        }
    ]


async def test_async_write_propagates_rejection(coordinator, fake):
    await coordinator.async_refresh()
    before = coordinator.data
    fake.ignore_writes.add(NODE_KNOB_BRIGHTNESS)

    with pytest.raises(NsdkWriteRejected):
        await coordinator.async_write(NODE_KNOB_BRIGHTNESS, NsdkValue.of_int(3))

    assert coordinator.data is before


async def test_async_write_output_toggle_rereads_speakers(coordinator, fake):
    await coordinator.async_refresh()
    fake.rows[SPEAKERS_PATH] = _speaker_list_without_speakers(fake)

    await coordinator.async_write(OUTPUT_TOGGLES["sonos"], NsdkValue.of_bool(False))

    assert coordinator.data.value(OUTPUT_TOGGLES["sonos"]).as_bool() is False
    assert coordinator.data.speakers == ()


async def test_async_activate_rereads_speakers_only_when_asked(coordinator, fake):
    await coordinator.async_refresh()
    chosen = next(s for s in coordinator.data.speakers if not s.preferred)
    selection = {"type": chosen.type, "id": chosen.id}
    # What the device lists once it takes the new default speaker.
    body = copy.deepcopy(fake.rows[SPEAKERS_PATH])
    for row in body["rows"]:
        row.pop("preferred", None)
        if row.get("id") == chosen.id:
            row["preferred"] = True
    fake.rows[SPEAKERS_PATH] = body

    await coordinator.async_activate(NODE_SET_DEFAULT_OUTPUT, selection)

    assert not next(s for s in coordinator.data.speakers if s.id == chosen.id).preferred

    await coordinator.async_activate(
        NODE_SET_DEFAULT_OUTPUT, selection, reread_speakers=True
    )

    assert fake.set_calls[-1] == {
        "path": NODE_SET_DEFAULT_OUTPUT,
        "role": "activate",
        "value": selection,
    }
    assert [s.id for s in coordinator.data.speakers if s.preferred] == [chosen.id]


async def test_stop_push_unsubscribes(coordinator, fake, aioclient_mock):
    await _start_push(coordinator, fake)
    await wait_for(lambda: _polled_queue_ids(aioclient_mock))
    (queue_id,) = _polled_queue_ids(aioclient_mock)

    await coordinator.async_stop_push()

    assert fake.subscribe_calls[-1] == {
        "queueId": queue_id,
        "subscribe": [],
        "unsubscribe": [
            {"path": path, "type": "itemWithValue"} for path in SUBSCRIBED_PATHS
        ],
    }
    calls = aioclient_mock.call_count
    await asyncio.sleep(0.05)
    assert aioclient_mock.call_count == calls  # no loop survives to poll again
