# ABOUTME: Tests for async_setup_entry/async_unload_entry and the coordinator's
# ABOUTME: async_shutdown override. Runs against FakeVictrola; nothing is mocked.
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victrola_stream.const import (
    DOMAIN,
    NODE_SERIAL,
    SUBSCRIBED_PATHS,
)
from tests.conftest import wait_for
from tests.fake_device import FakeVictrola


def _serial(fake: FakeVictrola) -> str:
    """The sanitized serial from tests/fixtures/get_data.json."""
    return fake.values[NODE_SERIAL][0]["string_"]


async def test_setup_and_unload(hass, fake):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: fake.host}, unique_id=_serial(fake)
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    await wait_for(lambda: fake.subscribe_calls)  # the push loop has subscribed

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert fake.subscribe_calls[-1]["unsubscribe"] == [
        {"path": path, "type": "itemWithValue"} for path in SUBSCRIBED_PATHS
    ]


async def test_setup_retries_when_offline(hass, fake):
    fake.offline = True
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: fake.host}, unique_id=_serial(fake)
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
