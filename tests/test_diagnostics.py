# ABOUTME: Tests for the diagnostics download: redacted entry and device state.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import json

from homeassistant.helpers.discovery_flow import DiscoveryKey

from custom_components.victrola_stream.const import NODE_KNOB_BRIGHTNESS, NODE_MAC
from custom_components.victrola_stream.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.conftest import fixture_serial, setup_entry

_FIXTURE_SSID = "example-wifi"  # tests/fixtures/get_data.json, network:info
_FIXTURE_MAC_PREFIX = "02:00:00:00:00:"  # shared by the fixture's mac/bssid fields
_FIXTURE_SPEAKER_ID = "RINCON_00000000001001400"  # get_rows.json, the preferred row
_FIXTURE_SPEAKER_TITLE = "Zone 10"

# manifest.json's zeroconf type; the mDNS instance name embeds the device's
# memberId. Sanitized placeholder uuid, distinct from the serial fixture.
_FIXTURE_ZEROCONF_TYPE = "_sues800device._tcp.local."
_FIXTURE_MDNS_NAME = (
    "stream1832victrola-00000000-0000-4000-8000-000000000002._sues800device._tcp.local."
)


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


async def test_diagnostics_redacts_discovery_keys(hass, fake):
    """entry.as_dict()'s discovery_keys holds a tuple of DiscoveryKey dataclasses.

    async_redact_data only recurses into Mapping and list, so a per-domain
    tuple passes through untouched unless "discovery_keys" itself is in the
    redact set. For a zeroconf-discovered entry that tuple holds the mDNS
    instance name, which embeds the device's memberId.
    """
    entry = await setup_entry(
        hass,
        fake,
        discovery_keys={
            "zeroconf": (
                DiscoveryKey(
                    domain="zeroconf",
                    key=(_FIXTURE_ZEROCONF_TYPE, _FIXTURE_MDNS_NAME),
                    version=1,
                ),
            )
        },
    )

    result = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(result)

    assert _FIXTURE_MDNS_NAME not in dumped
    assert "**REDACTED**" in dumped

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
