# ABOUTME: Tests for the select platform: output, default speaker and enum settings.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.victrola_stream.const import (
    NODE_RCA_MODE,
    NODE_SET_DEFAULT_OUTPUT,
    NODE_STREAMING_QUALITY,
    OUTPUT_TOGGLES,
    SPEAKERS_PATH,
)
from tests.conftest import entity_id_for, fixture_serial, setup_entry, wait_for
from tests.fake_device import FakeVictrola

_PREFERRED_ROW_ID = "RINCON_00000000000301400"


def _rows_without_speakers(fake: FakeVictrola) -> dict[str, Any]:
    """The speakerSelection body with every speaker row dropped.

    Matches what the device shows outside Sonos mode: headers and output
    toggles remain, but no row carries an id.
    """
    body = fake.rows[SPEAKERS_PATH]
    return {**body, "rows": [row for row in body["rows"] if "id" not in row]}


async def test_output_reports_current_mode(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "output")

    assert hass.states.get(entity_id).state == "sonos"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_output_select_writes_toggle(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "output")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "upnp"},
        blocking=True,
    )

    assert fake.set_calls[-1] == {
        "path": OUTPUT_TOGGLES["upnp"],
        "role": "value",
        "value": {"type": "bool_", "bool_": True},
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_speaker_options_and_current(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "default_speaker")

    state = hass.states.get(entity_id)
    assert state.attributes["options"] == [f"Zone {n}" for n in range(1, 14)]
    assert state.state == "Zone 10"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_speaker_select_sends_row_id(hass, fake):
    # Review Focus 3: odd characters in a title must reach the select as
    # clean text, and picking it must still send the right row id.
    rows = fake.rows[SPEAKERS_PATH]["rows"]
    renamed_row = next(row for row in rows if row.get("id") == _PREFERRED_ROW_ID)
    renamed_row["title"] = "Harper's Den + 2"

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "default_speaker")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "Harper's Den + 2"},
        blocking=True,
    )

    assert fake.set_calls[-1] == {
        "path": NODE_SET_DEFAULT_OUTPUT,
        "role": "activate",
        "value": {"type": "victrolaOutputSonos", "id": _PREFERRED_ROW_ID},
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_speaker_unavailable_outside_sonos_mode(hass, fake):
    # R8/Review Focus 5: the recorded fixture device sits in Sonos mode with
    # 13 Sonos rows. Switching output drops the rows to headers/toggles only.
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "default_speaker")
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    sonos_rows = fake.rows[SPEAKERS_PATH]
    fake.rows[SPEAKERS_PATH] = _rows_without_speakers(fake)
    fake.push_event(OUTPUT_TOGGLES["sonos"], {"type": "bool_", "bool_": False})
    fake.push_event(OUTPUT_TOGGLES["upnp"], {"type": "bool_", "bool_": True})

    await wait_for(lambda: hass.states.get(entity_id).state == STATE_UNAVAILABLE)

    fake.rows[SPEAKERS_PATH] = sonos_rows
    fake.push_event(OUTPUT_TOGGLES["upnp"], {"type": "bool_", "bool_": False})
    fake.push_event(OUTPUT_TOGGLES["sonos"], {"type": "bool_", "bool_": True})

    await wait_for(lambda: hass.states.get(entity_id).state != STATE_UNAVAILABLE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_enum_select_writes_typed_device_value(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "streaming_quality")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "sound_quality"},
        blocking=True,
    )

    assert fake.set_calls[-1] == {
        "path": NODE_STREAMING_QUALITY,
        "role": "value",
        "value": {"type": "forceLowBitrate", "forceLowBitrate": "soundQuality"},
    }
    assert hass.states.get(entity_id).state == "sound_quality"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_enum_unknown_device_value_reads_unknown(hass, fake):
    fake.values[NODE_RCA_MODE] = [
        {"type": "adchlsDACMode", "adchlsDACMode": "futureMode"}
    ]
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "select", serial, "rca_mode")

    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
