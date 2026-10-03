# ABOUTME: Switch platform: mute, autoplay and RCA fixed volume.
# ABOUTME: Each switch writes its node as a typed bool, confirmed by read-back.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NODE_AUTOPLAY, NODE_MUTE, NODE_RCA_FIXED_VOLUME
from .coordinator import VictrolaConfigEntry
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin
from .nsdk import NsdkValue


@dataclass(frozen=True, kw_only=True)
class VictrolaSwitchEntityDescription(
    SwitchEntityDescription, VictrolaEntityDescriptionMixin
):
    """node is both the switch's state and the path it writes."""


SWITCH_DESCRIPTIONS: tuple[VictrolaSwitchEntityDescription, ...] = (
    VictrolaSwitchEntityDescription(
        key="mute",
        translation_key="mute",
        node=NODE_MUTE,
    ),
    VictrolaSwitchEntityDescription(
        key="autoplay",
        translation_key="autoplay",
        node=NODE_AUTOPLAY,
        entity_category=EntityCategory.CONFIG,
    ),
    VictrolaSwitchEntityDescription(
        key="rca_fixed_volume",
        translation_key="rca_fixed_volume",
        node=NODE_RCA_FIXED_VOLUME,
        entity_category=EntityCategory.CONFIG,
    ),
)


class VictrolaSwitch(VictrolaEntity, SwitchEntity):
    """A boolean switch whose node is both its state and its write target."""

    entity_description: VictrolaSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.value(self.entity_description.node).as_bool()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(self.entity_description.node, NsdkValue.of_bool(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(self.entity_description.node, NsdkValue.of_bool(False))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one switch per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        VictrolaSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
        if description.exists(coordinator.data)
    )
