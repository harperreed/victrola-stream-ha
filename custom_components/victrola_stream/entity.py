# ABOUTME: Base entity and device card shared by every victrola_stream platform.
# ABOUTME: Entities read only the coordinator's VictrolaState; one source of truth.
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from homeassistant.exceptions import HomeAssistantError
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
from .nsdk import NsdkConnectionError, NsdkError, NsdkValue, NsdkWriteRejected


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


@asynccontextmanager
async def _translate_client_errors() -> AsyncIterator[None]:
    """Map the NSDK client's errors to a translated HomeAssistantError.

    NsdkWriteRejected -> write_rejected, NsdkConnectionError ->
    device_unreachable, any other NsdkError -> device_error.
    """
    try:
        yield
    except NsdkWriteRejected as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="write_rejected"
        ) from err
    except NsdkConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="device_unreachable"
        ) from err
    except NsdkError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="device_error",
            translation_placeholders={"error": str(err)},
        ) from err


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

    async def _async_write(self, path: str, value: NsdkValue) -> None:
        """Write a typed value through the coordinator; never optimistic.

        The entity's state only moves once the coordinator publishes the
        device's read-back.
        """
        async with _translate_client_errors():
            await self.coordinator.async_write(path, value)

    async def _async_activate(
        self, path: str, value: Any, *, reread_speakers: bool = False
    ) -> None:
        """Fire an action node through the coordinator."""
        async with _translate_client_errors():
            await self.coordinator.async_activate(
                path, value, reread_speakers=reread_speakers
            )
