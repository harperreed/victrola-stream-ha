# ABOUTME: Home Assistant entry point for the victrola_stream integration.
# ABOUTME: Builds the NSDK client and coordinator, then forwards to platforms.
from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import VictrolaConfigEntry, VictrolaCoordinator
from .nsdk import NsdkClient

# Tasks 8 and 9 add the switch/number/button/select platforms.
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VictrolaConfigEntry) -> bool:
    """Set up a Victrola Stream from a config entry."""
    client = NsdkClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    coordinator = VictrolaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    coordinator.async_start_push()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VictrolaConfigEntry) -> bool:
    """Unload the platforms, then stop the coordinator's push loop."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
