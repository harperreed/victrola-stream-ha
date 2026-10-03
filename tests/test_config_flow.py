# ABOUTME: Tests for VictrolaConfigFlow: user, zeroconf and reconfigure steps.
# ABOUTME: Runs against FakeVictrola's recorded payloads; nothing of ours is mocked.
import json
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_DEVICE_NAME,
    NODE_MANUFACTURER,
    NODE_SERIAL,
)
from tests.fake_device import FakeVictrola

# A serial that is never the fixture's, for the "wrong device" reconfigure case.
_OTHER_SERIAL = "00000000-0000-4000-8000-000000000099"
_INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "custom_components" / DOMAIN


def _strings() -> dict[str, Any]:
    return json.loads((_INTEGRATION_DIR / "strings.json").read_text())


def _serial(fake: FakeVictrola) -> str:
    """The sanitized serial from tests/fixtures/get_data.json."""
    return fake.values[NODE_SERIAL][0]["string_"]


def _device_name(fake: FakeVictrola) -> str:
    """The sanitized device name from tests/fixtures/get_data.json."""
    return fake.values[NODE_DEVICE_NAME][0]["string_"]


def _zeroconf_info(fake: FakeVictrola, **properties: Any) -> ZeroconfServiceInfo:
    """A ZeroconfServiceInfo like the sanitized mDNS capture, with overrides."""
    merged = {
        "name": _device_name(fake),
        "serial": _serial(fake),
        "uuid": "stream1832victrola-00000000-0000-4000-8000-000000000002",
        "manufacturer": "Victrola",
        "ip": fake.host,
        **properties,
    }
    return ZeroconfServiceInfo(
        ip_address=ip_address(fake.host),
        ip_addresses=[ip_address(fake.host)],
        port=80,
        hostname="victrola-stream.local.",
        type="_sues800device._tcp.local.",
        name=f"{merged['name']}._sues800device._tcp.local.",
        properties=merged,
    )


async def test_user_flow_creates_entry(hass, fake):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == _device_name(fake)
    assert result["data"] == {CONF_HOST: fake.host}
    assert result["result"].unique_id == _serial(fake)

    assert await hass.config_entries.async_unload(result["result"].entry_id)
    await hass.async_block_till_done()


async def test_user_flow_cannot_connect(hass, fake):
    fake.offline = True

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_not_victrola(hass, fake):
    fake.values[NODE_MANUFACTURER] = [{"type": "string_", "string_": "KEF"}]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_victrola"}


async def test_user_flow_already_configured(hass, fake):
    MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: fake.host}, unique_id=_serial(fake)
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_flow_creates_entry(hass, fake):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_zeroconf_info(fake),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == _device_name(fake)
    assert result["data"] == {CONF_HOST: fake.host}
    assert result["result"].unique_id == _serial(fake)

    assert await hass.config_entries.async_unload(result["result"].entry_id)
    await hass.async_block_till_done()


async def test_discovered_flow_title_names_the_turntable(hass, fake):
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf_info(fake)
    )

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    placeholders = flow["context"]["title_placeholders"]
    title = _strings()["config"]["flow_title"].format(**placeholders)
    assert title == _device_name(fake)


async def test_user_flow_aborts_while_a_discovery_is_pending(hass, fake):
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf_info(fake)
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"
    assert result["reason"] in _strings()["config"]["abort"]


def test_english_translation_mirrors_strings():
    strings = (_INTEGRATION_DIR / "strings.json").read_bytes()

    assert (_INTEGRATION_DIR / "translations" / "en.json").read_bytes() == strings


async def test_zeroconf_updates_host_of_existing_entry(hass, fake):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.99"}, unique_id=_serial(fake)
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_zeroconf_info(fake),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == fake.host


async def test_zeroconf_ignores_non_victrola(hass, fake):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_zeroconf_info(fake, manufacturer="KEF"),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_victrola"


async def test_reconfigure_changes_host(hass, fake):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.99"}, unique_id=_serial(fake)
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == fake.host

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_reconfigure_wrong_device_aborts(hass, fake):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.99"}, unique_id=_OTHER_SERIAL
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
