# ABOUTME: Button platform: restarts the turntable.
# ABOUTME: Fires powermanager:goReboot; the device drops offline and reconnects.
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NODE_REBOOT
from .coordinator import VictrolaConfigEntry
from .entity import VictrolaEntity, VictrolaEntityDescriptionMixin


@dataclass(frozen=True, kw_only=True)
class VictrolaButtonEntityDescription(
    ButtonEntityDescription, VictrolaEntityDescriptionMixin
):
    """node is the action path this button activates."""


BUTTON_DESCRIPTIONS: tuple[VictrolaButtonEntityDescription, ...] = (
    VictrolaButtonEntityDescription(
        key="restart",
        translation_key="restart",
        node=NODE_REBOOT,
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
    ),
)


class VictrolaButton(VictrolaEntity, ButtonEntity):
    """A button that activates its description's action node."""

    entity_description: VictrolaButtonEntityDescription

    async def async_press(self) -> None:
        await self._async_activate(self.entity_description.node, True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VictrolaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one button per description whose node exists on this device."""
    coordinator = entry.runtime_data
    async_add_entities(
        VictrolaButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
        if description.exists(coordinator.data)
    )
