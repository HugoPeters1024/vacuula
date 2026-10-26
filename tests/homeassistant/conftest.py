"""Enable the local custom integration in Home Assistant tests."""

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Load custom_components/vacuula during tests."""
