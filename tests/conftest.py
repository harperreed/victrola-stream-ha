# ABOUTME: Shared pytest fixtures for the victrola_stream test suite.
# ABOUTME: Lets HA's test harness load custom_components; shares fake/client fixtures.
import asyncio
from collections.abc import Callable

import pytest

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
