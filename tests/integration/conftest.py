"""Fixtures for integration tests that exercise real Jamf API calls.

Integration tests default to Jamf's publicly published dummy instance
(`dummy.jamfcloud.com`) so anyone running `make test-integration` gets
useful results without setup. To point the suite at your own test
tenant, set the three env vars below before invoking pytest:

    PATCHER_INTEGRATION_URL
    PATCHER_INTEGRATION_CLIENT_ID
    PATCHER_INTEGRATION_CLIENT_SECRET

The dummy instance credentials are documented at:
https://developer.jamf.com/jamf-pro/docs/populating-dummy-data
"""

from __future__ import annotations

import os

import pytest
from src.patcher.client.token_manager import TokenManager
from src.patcher.core.config_manager import ConfigManager

# Jamf's published, world-readable test instance. Safe to commit — these
# credentials are intentionally public and documented as such by Jamf.
_DUMMY_URL = "https://dummy.jamfcloud.com"
_DUMMY_CLIENT_ID = "2b7ea5e9-cbab-4f60-97e3-32eaefeee768"
_DUMMY_CLIENT_SECRET = "o0dwi8E0XMaYtX760LB05csjHeJoGHKldTi4R5x7NKwLMl25gYenpMAlRDerA6G1"


@pytest.fixture
def integration_url() -> str:
    """Jamf instance URL for integration tests. Override via PATCHER_INTEGRATION_URL."""
    return os.environ.get("PATCHER_INTEGRATION_URL", _DUMMY_URL)


@pytest.fixture
def integration_client_id() -> str:
    """OAuth client ID for integration tests. Override via PATCHER_INTEGRATION_CLIENT_ID."""
    return os.environ.get("PATCHER_INTEGRATION_CLIENT_ID", _DUMMY_CLIENT_ID)


@pytest.fixture
def integration_client_secret() -> str:
    """OAuth client secret for integration tests. Override via PATCHER_INTEGRATION_CLIENT_SECRET."""
    return os.environ.get("PATCHER_INTEGRATION_CLIENT_SECRET", _DUMMY_CLIENT_SECRET)


@pytest.fixture
def integration_config(
    integration_url: str,
    integration_client_id: str,
    integration_client_secret: str,
) -> ConfigManager:
    """A real ConfigManager in in-memory mode pointed at the test Jamf instance.

    Uses the CI/CD `in_memory_credentials` path so no keychain access is
    attempted (would fail on Linux CI / non-macOS environments anyway).
    """
    return ConfigManager(
        in_memory_credentials={
            "URL": integration_url,
            "CLIENT_ID": integration_client_id,
            "CLIENT_SECRET": integration_client_secret,
        }
    )


@pytest.fixture
def integration_token_manager(integration_config: ConfigManager) -> TokenManager:
    """A real TokenManager configured against the integration instance."""
    return TokenManager(integration_config)
