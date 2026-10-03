# ABOUTME: Tests for the binary_sensor platform: platter motor and streaming session.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE

from custom_components.victrola_stream.const import (
    NODE_MOTOR,
    NODE_SONOS_SESSION,
    OUTPUT_TOGGLES,
)
from tests.conftest import entity_id_for, fixture_serial, setup_entry, wait_for


def _bool_value(value: bool) -> list[dict]:
    return [{"type": "bool_", "bool_": value}]


async def test_platter_follows_events(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "binary_sensor", serial, "platter_spinning")
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    fake.push_event(NODE_MOTOR, {"type": "bool_", "bool_": False})
    await wait_for(lambda: hass.states.get(entity_id).state == STATE_OFF)

    fake.push_event(NODE_MOTOR, {"type": "bool_", "bool_": True})
    await wait_for(lambda: hass.states.get(entity_id).state == STATE_ON)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_streaming_on_in_sonos_mode(hass, fake):
    # The fixture's own output is already Sonos; only the session needs to be live.
    fake.values[NODE_SONOS_SESSION] = _bool_value(True)

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "binary_sensor", serial, "streaming")

    assert hass.states.get(entity_id).state == STATE_ON

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_streaming_unavailable_in_roon_mode(hass, fake):
    fake.values[OUTPUT_TOGGLES["sonos"]] = _bool_value(False)
    fake.values[OUTPUT_TOGGLES["roon"]] = _bool_value(True)

    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "binary_sensor", serial, "streaming")

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
