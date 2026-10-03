# ABOUTME: Tests for the diagnostics download: redacted entry and device state.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import json

from custom_components.victrola_stream.const import NODE_KNOB_BRIGHTNESS, NODE_MAC
from custom_components.victrola_stream.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.conftest import fixture_serial, setup_entry

_FIXTURE_SSID = "example-wifi"  # tests/fixtures/get_data.json, network:info
_FIXTURE_MAC_PREFIX = "02:00:00:00:00:"  # shared by the fixture's mac/bssid fields
_FIXTURE_SPEAKER_ID = "RINCON_00000000001001400"  # get_rows.json, the preferred row
_FIXTURE_SPEAKER_TITLE = "Zone 10"


async def test_diagnostics_redacts_private_values(hass, fake):
    entry = await setup_entry(hass, fake)
    serial = fixture_serial(fake)
    mac = fake.values[NODE_MAC][0]["string_"]

    result = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(result)

    assert serial not in dumped
    assert mac not in dumped
    assert _FIXTURE_MAC_PREFIX not in dumped
    assert _FIXTURE_SSID not in dumped
    assert _FIXTURE_SPEAKER_ID not in dumped
    assert _FIXTURE_SPEAKER_TITLE not in dumped
    assert "**REDACTED**" in dumped
    assert result["state"]["values"][NODE_KNOB_BRIGHTNESS] == {
        "type": "i32_",
        "i32_": 7,
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
