# ABOUTME: Binary sensor platform: platter motor and the current streaming session.
# ABOUTME: Read-only; every value comes from the coordinator's VictrolaState.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    NODE_MOTOR,
    NODE_SONOS_SESSION,
    NODE_UPNP_STATE,
    UPNP_STREAMING_STATES,
)
from .coordinator import VictrolaConfigEntry, VictrolaState
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin


def _platter_spinning(state: VictrolaState) -> bool | None:
    return state.value(NODE_MOTOR).as_bool()


def _streaming_available(state: VictrolaState) -> bool:
    """Only Sonos and UPnP mode report a streaming session today."""
    return state.output in ("sonos", "upnp")


def _streaming(state: VictrolaState) -> bool | None:
    if state.output == "sonos":
        return state.value(NODE_SONOS_SESSION).as_bool()
    if state.output == "upnp":
        return state.value(NODE_UPNP_STATE).payload in UPNP_STREAMING_STATES
    return None


@dataclass(frozen=True, kw_only=True)
class VictrolaBinarySensorEntityDescription(
    BinarySensorEntityDescription, VictrolaEntityDescriptionMixin
):
    value_fn: Callable[[VictrolaState], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[VictrolaBinarySensorEntityDescription, ...] = (
    VictrolaBinarySensorEntityDescription(
        key="platter_spinning",
        translation_key="platter_spinning",
        node=NODE_MOTOR,
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_platter_spinning,
    ),
    VictrolaBinarySensorEntityDescription(
        key="streaming",
        translation_key="streaming",
        available_fn=_streaming_available,
        value_fn=_streaming,
    ),
)


class VictrolaBinarySensor(VictrolaEntity, BinarySensorEntity):
    """A read-only binary sensor driven entirely by its description's value_fn."""

    entity_description: VictrolaBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one binary sensor per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        VictrolaBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.exists(coordinator.data)
    )
