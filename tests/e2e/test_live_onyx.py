# ABOUTME: Live end-to-end suite against the real Victrola Stream turntable.
# ABOUTME: Skipped unless $VICTROLA_HOST is set; never uses aioclient_mock or the fake.
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from typing import Any

import pytest
from homeassistant.components.media_source import (
    Unresolvable,
    async_resolve_media,
    generate_media_source_id,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.setup import async_setup_component

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_KNOB_BRIGHTNESS,
    NODE_MOTOR,
    NODE_SERIAL,
    NODE_SONOS_SESSION,
    URL_PATHS,
)
from custom_components.victrola_stream.nsdk import NsdkClient, NsdkValue
from tests.conftest import entity_id_for, wait_for
from tests.e2e.conftest import setup_live_entry, teardown_live_entry

# URL_PATHS key -> the content type the live stream must answer with.
_EXPECTED_CONTENT_TYPES: Mapping[str, str] = {
    "hls": "application/vnd.apple.mpegurl",
    "mp3": "audio/mpeg",
    "flac": "audio/ogg",
}

_STREAM_READ_BYTES = 65536
_STREAM_READ_TIMEOUT_S = 5
_SONOS_DELAY_OPTIONS = ("min", "med", "high", "max")


def _ffprobe_audio_stream(data: bytes) -> dict[str, Any]:
    """Decode a captured chunk's first audio stream with ffprobe."""
    with tempfile.NamedTemporaryFile(suffix=".flac") as tmp:
        tmp.write(data)
        tmp.flush()
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,bits_per_raw_sample",
                "-of",
                "json",
                tmp.name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    return json.loads(result.stdout)["streams"][0]


async def test_live_config_flow_and_entities(
    hass: HomeAssistant, victrola_host: str
) -> None:
    """The user config flow against the real device creates a live entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: victrola_host}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()

    try:
        serial = entry.runtime_data.data.value(NODE_SERIAL).as_str()
        assert serial

        platter_id = entity_id_for(hass, "binary_sensor", serial, "platter_spinning")
        assert hass.states.get(platter_id).state in (STATE_ON, STATE_OFF)

        wifi_id = entity_id_for(hass, "sensor", serial, "wifi_signal")
        assert int(hass.states.get(wifi_id).state) < 0
    finally:
        await teardown_live_entry(hass, entry)


async def test_live_brightness_roundtrip(
    hass: HomeAssistant, victrola_host: str
) -> None:
    """A change made outside HA arrives over the push path, and HA's own
    write still round-trips through the device's typed read-back."""
    entry = await setup_live_entry(hass, victrola_host)
    try:
        coordinator = entry.runtime_data
        serial = coordinator.data.value(NODE_SERIAL).as_str()
        entity_id = entity_id_for(hass, "number", serial, "knob_brightness")

        original = coordinator.data.value(NODE_KNOB_BRIGHTNESS).as_int()
        assert original is not None
        changed = original - 1 if original == 100 else original + 1

        try:
            # A second, independent client -- not the coordinator's write
            # path -- so the only way HA can learn about this is its event
            # queue subscription, not a round trip HA itself initiated.
            external_client = NsdkClient(async_get_clientsession(hass), victrola_host)
            await external_client.set_typed(
                NODE_KNOB_BRIGHTNESS, NsdkValue.of_int(changed)
            )

            await wait_for(
                lambda: (
                    coordinator.data.value(NODE_KNOB_BRIGHTNESS).as_int() == changed
                ),
                timeout=10,
            )
            assert hass.states.get(entity_id).state == str(changed)
        finally:
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": original},
                blocking=True,
            )
            assert hass.states.get(entity_id).state == str(original)
    finally:
        await teardown_live_entry(hass, entry)


async def test_live_stream_urls_answer(hass: HomeAssistant, victrola_host: str) -> None:
    """Every populated stream URL answers with its documented content type.

    gotchas.md: every adchls:serverUrl* node reads "" whenever no streaming
    session is active -- network standby after ~10 idle minutes is one case,
    not the only one. An empty URL is "no stream right now", not an error, so
    each format skips rather than fails when that is caught mid-loop.
    """
    entry = await setup_live_entry(hass, victrola_host)
    try:
        session = async_get_clientsession(hass)
        flac_audio = b""

        for fmt, expected_type in _EXPECTED_CONTENT_TYPES.items():
            url = entry.runtime_data.data.stream_url(fmt)
            if not url:
                pytest.skip(f"no streaming session right now: no {fmt} stream")
            async with session.get(url) as resp:
                assert resp.status == 200
                assert resp.content_type == expected_type
                if fmt == "flac":
                    # .read(n) returns as soon as any data is in the buffer,
                    # which can be a single ~4 KiB TCP read -- far too little
                    # for ffprobe to find a stream. readexactly() accumulates
                    # until it has the full 64 KiB or the 5 s deadline hits.
                    try:
                        async with asyncio.timeout(_STREAM_READ_TIMEOUT_S):
                            flac_audio = await resp.content.readexactly(
                                _STREAM_READ_BYTES
                            )
                    except TimeoutError, asyncio.IncompleteReadError:
                        flac_audio = b""  # didn't get the full 64 KiB in time

        if not flac_audio:
            pytest.skip("no record playing: no FLAC audio arrived within 5 s")

        stream = await hass.async_add_executor_job(_ffprobe_audio_stream, flac_audio)
        assert stream["codec_name"] == "flac"
        assert stream["bits_per_raw_sample"] == "24"
    finally:
        await teardown_live_entry(hass, entry)


async def test_live_media_source_resolves_current_url(
    hass: HomeAssistant, victrola_host: str
) -> None:
    """Resolving the flac source matches a fresh adchls:serverUrl/flac read.

    With no streaming session right now that fresh read is "" and
    media_source.py raises Unresolvable (gotchas.md: an empty URL means no
    stream right now, not an error) -- pin both branches live rather than
    skip the no-session one.
    """
    await async_setup_component(hass, "media_source", {})
    entry = await setup_live_entry(hass, victrola_host)
    try:
        # Independent of media_source.py's own internal read, so this checks
        # what the device actually has right now, not the same call twice.
        independent_client = NsdkClient(async_get_clientsession(hass), victrola_host)
        fresh = await independent_client.get_value(URL_PATHS["flac"])
        media_source_id = generate_media_source_id(DOMAIN, f"{entry.entry_id}/flac")

        if fresh.as_str():
            played = await async_resolve_media(hass, media_source_id, None)
            assert played.url == fresh.as_str()
            assert played.mime_type == "audio/ogg"
        else:
            with pytest.raises(Unresolvable):
                await async_resolve_media(hass, media_source_id, None)
    finally:
        await teardown_live_entry(hass, entry)


@pytest.mark.skipif(
    not os.environ.get("VICTROLA_E2E_ENUM_WRITE"),
    reason="touches audio settings; opt in only with the turntable idle",
)
async def test_live_enum_write_roundtrip(
    hass: HomeAssistant, victrola_host: str
) -> None:
    """sonos_audio_delay round-trips to another option and back.

    Deferred to the human checklist whenever the turntable is not idle: a
    record playing or an active Sonos session means changing the audio
    delay could audibly glitch what is currently playing.
    """
    entry = await setup_live_entry(hass, victrola_host)
    try:
        state = entry.runtime_data.data
        is_playing = state.value(NODE_MOTOR).as_bool()
        has_session = state.value(NODE_SONOS_SESSION).as_bool()
        if is_playing or has_session:
            pytest.skip(
                "deferred to the live checklist: turntable is not idle "
                f"(motorDet={is_playing!r}, isConnectedToSonosGroup={has_session!r})"
            )

        serial = state.value(NODE_SERIAL).as_str()
        entity_id = entity_id_for(hass, "select", serial, "sonos_audio_delay")
        original = hass.states.get(entity_id).state
        other = next(o for o in _SONOS_DELAY_OPTIONS if o != original)

        try:
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": other},
                blocking=True,
            )
            assert hass.states.get(entity_id).state == other
        finally:
            await hass.services.async_call(
                "select",
                "select_option",
                {"entity_id": entity_id, "option": original},
                blocking=True,
            )
            assert hass.states.get(entity_id).state == original
    finally:
        await teardown_live_entry(hass, entry)
