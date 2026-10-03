# ABOUTME: Tests for the button platform: the device restart button.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
from custom_components.victrola_stream.const import NODE_REBOOT
from tests.conftest import entity_id_for, fixture_serial, setup_entry


async def test_restart_button_activates_reboot(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    entity_id = entity_id_for(hass, "button", serial, "restart")

    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )

    assert fake.set_calls[-1] == {
        "path": NODE_REBOOT,
        "role": "activate",
        "value": True,
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
