# ABOUTME: Tests for the number platform: volume, knob brightness and RCA delay.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from homeassistant.components.number import NumberMode
from homeassistant.const import STATE_UNAVAILABLE

from custom_components.victrola_stream.const import (
    NODE_KNOB_BRIGHTNESS,
    NODE_SONOS_SESSION,
    NODE_VOLUME,
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


async def test_rca_delay_is_a_slider(hass, fake):
    # The device's own settings metadata marks adchls/dacDelay a slider.
    entry = await setup_entry(hass, fake)
    entity_id = entity_id_for(hass, "number", fixture_serial(fake), "rca_delay")

    assert hass.states.get(entity_id).attributes["mode"] == NumberMode.SLIDER

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_volume_available_during_sonos_session(hass, fake):
    # R21: the recorded fixture device sits in Sonos mode with no active
    # session, where player:volume has no live value. A Sonos session makes
    # it track the group volume, writes still send a typed int, and it goes
    # unavailable again once the session ends.
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "number", serial, "volume")
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    fake.push_event(NODE_SONOS_SESSION, {"type": "bool_", "bool_": True})
    await wait_for(lambda: hass.states.get(entity_id).state != STATE_UNAVAILABLE)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 17}, blocking=True
    )
    assert fake.set_calls[-1] == {
        "path": NODE_VOLUME,
        "role": "value",
        "value": {"type": "i32_", "i32_": 17},
    }

    fake.push_event(NODE_SONOS_SESSION, {"type": "bool_", "bool_": False})
    await wait_for(lambda: hass.states.get(entity_id).state == STATE_UNAVAILABLE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
