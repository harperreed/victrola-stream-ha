# ABOUTME: Shared pytest fixtures for the victrola_stream test suite.
# ABOUTME: Lets Home Assistant's test harness load this repo's custom_components.
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
