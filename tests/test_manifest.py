# ABOUTME: Verifies Home Assistant can discover and load the victrola_stream manifest.
# ABOUTME: Pins the exact metadata values the integration must publish.
from homeassistant.loader import async_get_integration

from custom_components.victrola_stream.const import DOMAIN


async def test_manifest_is_discoverable(hass):
    m = (await async_get_integration(hass, DOMAIN)).manifest
    assert (m["version"], m["iot_class"], m["integration_type"]) == (
        "0.1.0",
        "local_push",
        "device",
    )
    assert (
        m["config_flow"] is True
        and m["requirements"] == []
        and m["codeowners"] == ["@harperreed"]
    )
    assert m["zeroconf"] == [
        {
            "type": "_sues800device._tcp.local.",
            "properties": {"manufacturer": "victrola"},
        }
    ]
