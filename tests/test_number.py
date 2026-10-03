# ABOUTME: Tests for the number platform: volume, knob brightness and RCA delay.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from homeassistant.const import STATE_UNAVAILABLE

from custom_components.victrola_stream.const import (
    NODE_KNOB_BRIGHTNESS,
    OUTPUT_TOGGLES,
)
from tests.conftest import entity_id_for, fixture_serial, setup_entry, wait_for


async def test_number_sends_typed_int(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "number", serial, "knob_brightness")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 17}, blocking=True
    )

    assert fake.set_calls[-1] == {
        "path": NODE_KNOB_BRIGHTNESS,
        "role": "value",
        "value": {"type": "i32_", "i32_": 17},
    }
    assert hass.states.get(entity_id).state == "17"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_volume_unavailable_in_sonos_mode(hass, fake):
    # R8/Review Focus 5: the recorded fixture device sits in Sonos mode, where
    # player:volume has no live value; only UPnP/Bluetooth output exposes it.
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "number", serial, "volume")
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    fake.push_event(OUTPUT_TOGGLES["upnp"], {"type": "bool_", "bool_": True})
    fake.push_event(OUTPUT_TOGGLES["sonos"], {"type": "bool_", "bool_": False})

    await wait_for(lambda: hass.states.get(entity_id).state != STATE_UNAVAILABLE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
