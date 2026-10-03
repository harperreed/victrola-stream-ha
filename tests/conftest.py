# ABOUTME: Shared pytest fixtures for the victrola_stream test suite.
# ABOUTME: Lets HA's test harness load custom_components; shares fake/client fixtures.
import pytest

from custom_components.victrola_stream.nsdk import NsdkClient
from tests.fake_device import FakeVictrola


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
