# ABOUTME: Base entity and device card shared by every victrola_stream platform.
# ABOUTME: Entities read only the coordinator's VictrolaState; one source of truth.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NODE_DEVICE_NAME,
    NODE_FIRMWARE,
    NODE_MAC,
    NODE_MANUFACTURER,
    NODE_MCU_FIRMWARE,
    NODE_PRODUCT,
    NODE_SERIAL,
)
from .coordinator import VictrolaCoordinator, VictrolaState


def device_info(state: VictrolaState, host: str) -> DeviceInfo:
    """The device registry entry for one turntable."""
    serial = state.value(NODE_SERIAL).as_str() or ""
    mac = state.value(NODE_MAC).as_str() or ""
    return DeviceInfo(
        identifiers={(DOMAIN, serial)},
        connections={(CONNECTION_NETWORK_MAC, mac.lower())},
        manufacturer=state.value(NODE_MANUFACTURER).as_str(),
        model=state.value(NODE_PRODUCT).as_str(),
        name=state.value(NODE_DEVICE_NAME).as_str(),
        sw_version=state.value(NODE_FIRMWARE).as_str(),
        hw_version=state.value(NODE_MCU_FIRMWARE).as_str(),
        serial_number=serial,
        configuration_url=f"http://{host}/webclient/",
    )


def _always_available(_state: VictrolaState) -> bool:
    return True


@dataclass(frozen=True, kw_only=True)
class VictrolaEntityDescriptionMixin:
    """Extra fields every Victrola entity description carries.

    node: the node this entity reads or writes, if it has a single one.
    exists_fn: does the entity get created at setup? None falls back to the
        default rule: "node is None, or node isn't in state.missing".
    available_fn: is the entity available right now? Default: always.
    """

    node: str | None = None
    exists_fn: Callable[[VictrolaState], bool] | None = None
    available_fn: Callable[[VictrolaState], bool] = _always_available

    def exists(self, state: VictrolaState) -> bool:
        """Should this description's entity be created at setup?"""
        if self.exists_fn is not None:
            return self.exists_fn(state)
        return self.node is None or self.node not in state.missing


class VictrolaEntity(CoordinatorEntity[VictrolaCoordinator]):
    """Base for every Victrola Stream entity: device card, id and availability."""

    _attr_has_entity_name = True

    entity_description: VictrolaEntityDescriptionMixin

    def __init__(
        self,
        coordinator: VictrolaCoordinator,
        description: VictrolaEntityDescriptionMixin,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.data.value(NODE_SERIAL).as_str() or ""
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = device_info(coordinator.data, coordinator.client.host)

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(
            self.coordinator.data
        )
