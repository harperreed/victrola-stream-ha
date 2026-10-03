# ABOUTME: Diagnostics download: a redacted snapshot of the config entry and state.
# ABOUTME: Strips identity, network and Sonos details so a bug report leaks nothing.
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import NODE_MAC, NODE_SERIAL, URL_PATHS
from .coordinator import VictrolaConfigEntry, VictrolaState

TO_REDACT = frozenset(
    {
        # Node paths whose value identifies this device or its network.
        NODE_SERIAL,
        NODE_MAC,
        "settings:/system/memberId",
        *URL_PATHS.values(),
        # Nested keys inside network:info and the speaker rows.
        "ssid",
        "bssid",
        "mac",
        "addresses",
        "ip",
        "gateways",
        "dns",
        "id",
        "title",
        "householdId",
        "leader",
    }
)


def _state_dict(state: VictrolaState) -> dict[str, Any]:
    return {
        "values": {path: value.to_json() for path, value in state.values.items()},
        "missing": sorted(state.missing),
        "speakers": [asdict(speaker) for speaker in state.speakers],
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VictrolaConfigEntry
) -> dict[str, Any]:
    """Return a redacted snapshot of the config entry and device state."""
    return {
        "entry": async_redact_data(entry.as_dict(), {"host", "unique_id", "title"}),
        "state": async_redact_data(_state_dict(entry.runtime_data.data), TO_REDACT),
    }
