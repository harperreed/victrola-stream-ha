# ABOUTME: Shared pytest fixtures for the victrola_stream test suite.
# ABOUTME: Lets HA's test harness load custom_components; shares fake/client fixtures.
import asyncio
from collections.abc import Callable

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victrola_stream.const import DOMAIN, NODE_SERIAL
from custom_components.victrola_stream.nsdk import NsdkClient
from tests.fake_device import FakeVictrola

_WAIT_STEP_S = 0.01


# ASYNC109 wants callers to own timeouts; this helper's one job is a bounded wait.
async def wait_for(predicate: Callable[[], object], timeout: float = 2.0) -> None:  # noqa: ASYNC109
    """Poll predicate() every 0.01 s until it holds; fail the test after timeout s.

    Counts steps rather than reading a clock, so a test that freezes time
    still times out.
    """
    for _ in range(round(timeout / _WAIT_STEP_S)):
        if predicate():
            return
        await asyncio.sleep(_WAIT_STEP_S)
    if not predicate():
        pytest.fail(f"condition still false after {timeout} s")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake(aioclient_mock):
    return FakeVictrola(aioclient_mock)


@pytest.fixture
async def client(hass, aioclient_mock, fake):
    session = aioclient_mock.create_session(hass.loop)
    try:
        yield NsdkClient(session, fake.host)
    finally:
        await session.close()


def fixture_serial(fake: FakeVictrola) -> str:
    """The sanitized serial from tests/fixtures/get_data.json."""
    return fake.values[NODE_SERIAL][0]["string_"]


async def setup_entry(hass: HomeAssistant, fake: FakeVictrola) -> MockConfigEntry:
    """Add a config entry for fake to hass and set it up. The caller unloads it."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: fake.host}, unique_id=fixture_serial(fake)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id_for(
    hass: HomeAssistant, platform: str, serial: str, key: str
) -> str | None:
    """The entity_id the registry assigned the given platform/key for serial."""
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{serial}_{key}")
