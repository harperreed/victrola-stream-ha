# ABOUTME: Number platform: volume, knob brightness and RCA delay.
# ABOUTME: Each number writes its node as a typed int, confirmed by read-back.
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NODE_KNOB_BRIGHTNESS, NODE_RCA_DELAY, NODE_SONOS_SESSION, NODE_VOLUME
from .coordinator import VictrolaConfigEntry, VictrolaState
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin
from .nsdk import NsdkValue


def _volume_available(state: VictrolaState) -> bool:
    """player:volume carries a live value in UPnP/Bluetooth output always,
    and in Sonos output only while a Sonos streaming session is connected.
    """
    return state.output in ("upnp", "bluetooth") or (
        state.output == "sonos" and state.value(NODE_SONOS_SESSION).as_bool() is True
    )


@dataclass(frozen=True, kw_only=True)
class VictrolaNumberEntityDescription(
    NumberEntityDescription, VictrolaEntityDescriptionMixin
):
    """node is both the number's value and the path it writes."""


NUMBER_DESCRIPTIONS: tuple[VictrolaNumberEntityDescription, ...] = (
    VictrolaNumberEntityDescription(
        key="volume",
        translation_key="volume",
        node=NODE_VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        available_fn=_volume_available,
    ),
    VictrolaNumberEntityDescription(
        key="knob_brightness",
        translation_key="knob_brightness",
        node=NODE_KNOB_BRIGHTNESS,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    VictrolaNumberEntityDescription(
        key="rca_delay",
        translation_key="rca_delay",
        node=NODE_RCA_DELAY,
        native_min_value=0,
        native_max_value=500,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
)


class VictrolaNumber(VictrolaEntity, NumberEntity):
    """A number whose node is both its value and its write target."""

    entity_description: VictrolaNumberEntityDescription

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.value(self.entity_description.node).as_int()

    async def async_set_native_value(self, value: float) -> None:
        await self._async_write(
            self.entity_description.node, NsdkValue.of_int(int(value))
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one number per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        VictrolaNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
        if description.exists(coordinator.data)
    )
