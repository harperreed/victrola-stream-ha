# ABOUTME: Tests for the switch platform: mute, autoplay and RCA fixed volume.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.victrola_stream.const import NODE_AUTOPLAY
from tests.conftest import entity_id_for, fixture_serial, setup_entry


def _bool_value(value: bool) -> list[dict]:
    return [{"type": "bool_", "bool_": value}]


async def test_switch_turn_on_sends_typed_bool(hass, fake):
    fake.values[NODE_AUTOPLAY] = _bool_value(False)
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "switch", serial, "autoplay")

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )

    assert fake.set_calls[-1] == {
        "path": NODE_AUTOPLAY,
        "role": "value",
        "value": {"type": "bool_", "bool_": True},
    }
    assert hass.states.get(entity_id).state == "on"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_switch_write_rejected_raises_and_keeps_state(hass, fake):
    fake.values[NODE_AUTOPLAY] = _bool_value(False)
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "switch", serial, "autoplay")
    fake.ignore_writes.add(NODE_AUTOPLAY)

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": entity_id}, blocking=True
        )

    assert exc_info.value.translation_key == "write_rejected"
    assert hass.states.get(entity_id).state == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
