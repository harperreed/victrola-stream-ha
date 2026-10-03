# ABOUTME: Sensor platform: Wi-Fi signal, power state and the three stream URLs.
# ABOUTME: Read-only; every value comes from the coordinator's VictrolaState.
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import NODE_NETWORK, NODE_POWER, NODE_RSSI_EVENT, URL_PATHS
from .coordinator import VictrolaConfigEntry, VictrolaState
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin

_LOGGER = logging.getLogger(__name__)

# powermanager:target .target values mapped to the power_state sensor's options.
_POWER_STATES = {
    "online": "online",
    "networkStandby": "network_standby",
}
# The repr of each unmapped target already logged, so each is logged once.
_WARNED_POWER_TARGETS: set[str] = set()


def _wifi_signal(state: VictrolaState) -> int | None:
    """The latest network:wirelessRssi event, else network:info's signalLevel.

    An event that doesn't hold an int (a double_, say) falls back too.
    """
    rssi = state.value(NODE_RSSI_EVENT).as_int()
    # as_int hands back an int-typed value's payload unchecked, and the
    # device's JSON is not trusted, so check that it really is an int.
    if isinstance(rssi, int):
        return rssi
    network = state.value(NODE_NETWORK).payload
    if not isinstance(network, dict):
        return None
    wireless = network.get("wireless")
    return wireless.get("signalLevel") if isinstance(wireless, dict) else None


def _power_state(state: VictrolaState) -> str | None:
    """powermanager:target's .target, mapped to this sensor's options.

    Every state write lands here, so an unmapped target is logged only the
    first time it turns up, not on every write.
    """
    payload = state.value(NODE_POWER).payload
    target = payload.get("target") if isinstance(payload, dict) else None
    # Only a string can be a key; anything else the device sends is unmapped.
    mapped = _POWER_STATES.get(target) if isinstance(target, str) else None
    if mapped is None and repr(target) not in _WARNED_POWER_TARGETS:
        _WARNED_POWER_TARGETS.add(repr(target))
        _LOGGER.warning("Unknown power target: %r", target)
    return mapped


@dataclass(frozen=True, kw_only=True)
class VictrolaSensorEntityDescription(
    SensorEntityDescription, VictrolaEntityDescriptionMixin
):
    value_fn: Callable[[VictrolaState], StateType]


SENSOR_DESCRIPTIONS: tuple[VictrolaSensorEntityDescription, ...] = (
    VictrolaSensorEntityDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        node=NODE_NETWORK,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_wifi_signal,
    ),
    VictrolaSensorEntityDescription(
        key="power_state",
        translation_key="power_state",
        node=NODE_POWER,
        device_class=SensorDeviceClass.ENUM,
        options=["online", "network_standby"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_power_state,
    ),
    VictrolaSensorEntityDescription(
        key="stream_url_hls",
        translation_key="stream_url_hls",
        node=URL_PATHS["hls"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.stream_url("hls"),
    ),
    VictrolaSensorEntityDescription(
        key="stream_url_mp3",
        translation_key="stream_url_mp3",
        node=URL_PATHS["mp3"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.stream_url("mp3"),
    ),
    VictrolaSensorEntityDescription(
        key="stream_url_flac",
        translation_key="stream_url_flac",
        node=URL_PATHS["flac"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.stream_url("flac"),
    ),
)


class VictrolaSensor(VictrolaEntity, SensorEntity):
    """A read-only sensor driven entirely by its description's value_fn."""

    entity_description: VictrolaSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one sensor per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        VictrolaSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
        if description.exists(coordinator.data)
    )
