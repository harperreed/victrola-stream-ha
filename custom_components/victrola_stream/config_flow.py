# ABOUTME: Config flow for victrola_stream: user, zeroconf and reconfigure steps.
# ABOUTME: Identifies the device via its NSDK identity nodes before saving an entry.
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, NODE_DEVICE_NAME, NODE_MANUFACTURER, NODE_SERIAL
from .nsdk import EMPTY, NsdkClient, NsdkConnectionError, NsdkError, NsdkValue

_STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


async def _async_probe(
    hass: HomeAssistant, host: str, paths: tuple[str, ...]
) -> tuple[dict[str, NsdkValue], str | None]:
    """Read identity nodes from the device at host.

    Returns the values read and an error code, "cannot_connect" or
    "not_victrola", or None once the device identifies as a Victrola.
    """
    client = NsdkClient(async_get_clientsession(hass), host)
    try:
        values, _missing = await client.read_nodes(paths)
    except NsdkConnectionError, NsdkError:
        return {}, "cannot_connect"
    if values.get(NODE_MANUFACTURER, EMPTY).as_str() != "Victrola":
        return values, "not_victrola"
    return values, None


class VictrolaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Victrola Stream."""

    VERSION = 1

    _discovered_host: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manually entered host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            values, error = await _async_probe(
                self.hass, host, (NODE_SERIAL, NODE_MANUFACTURER, NODE_DEVICE_NAME)
            )
            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(values.get(NODE_SERIAL, EMPTY).as_str())
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=values.get(NODE_DEVICE_NAME, EMPTY).as_str() or host,
                    data={CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="user", data_schema=_STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered over mDNS."""
        properties = discovery_info.properties
        if properties.get("manufacturer", "").lower() != "victrola":
            return self.async_abort(reason="not_victrola")
        serial = properties.get("serial")
        if not serial:
            return self.async_abort(reason="cannot_connect")

        host = str(discovery_info.ip_address)
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self.context["title_placeholders"] = {
            "name": properties.get("name", "Victrola")
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a device discovered over mDNS."""
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data={CONF_HOST: self._discovered_host},
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a change of host for an existing entry."""
        errors: dict[str, str] = {}
        current_host = self._get_reconfigure_entry().data[CONF_HOST]
        if user_input is not None:
            host = user_input[CONF_HOST]
            values, error = await _async_probe(
                self.hass, host, (NODE_SERIAL, NODE_MANUFACTURER)
            )
            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(values.get(NODE_SERIAL, EMPTY).as_str())
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(), data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=current_host): str}
            ),
            errors=errors,
        )
