# ABOUTME: Fixtures for the live Onyx suite: collection skip and socket unblocking.
# ABOUTME: Every test talks to the real device at $VICTROLA_HOST; no aioclient_mock.
from __future__ import annotations

import os

import pytest
import pytest_socket
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.victrola_stream.const import DOMAIN

# Skip collecting the live suite entirely unless a device is configured, so
# `scripts/check` (run with no VICTROLA_HOST) never touches a socket and
# never shows even a skipped test for it.
collect_ignore = [] if os.environ.get("VICTROLA_HOST") else ["test_live_onyx.py"]


@pytest.fixture
def victrola_host() -> str:
    """The real device's IP, from $VICTROLA_HOST. Never hardcode it."""
    return os.environ["VICTROLA_HOST"]


@pytest.fixture(autouse=True)
def _unblock_victrola_socket(victrola_host: str):
    """Let real sockets reach the device and 127.0.0.1, and nothing else.

    phacc's own pytest_runtest_setup (plugins.py ~line 195) runs for every
    test and unconditionally calls socket_allow_hosts(["127.0.0.1"]) then
    disable_socket(allow_unix_socket=True). The second call replaces
    socket.socket with a guard whose __new__ rejects any non-Unix socket
    outright, before a connect()-level allow-list is ever consulted, so
    socket_allow_hosts alone cannot let a real TCP connection out. See
    gotchas.md for the measurement that led to adding enable_socket() here.
    """
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts([victrola_host, "127.0.0.1"])
    yield


async def setup_live_entry(hass: HomeAssistant, host: str) -> MockConfigEntry:
    """Add a config entry for the real device at host and set it up."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: host}, unique_id=host)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def teardown_live_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Unload a live entry so its push loop stops and unsubscribes cleanly."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
