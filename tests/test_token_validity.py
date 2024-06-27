import pytest
from unittest.mock import patch
from aioresponses import aioresponses
from datetime import datetime, timedelta, timezone
from src.client.token_manager import TokenManager
from src.client.config_manager import ConfigManager
from src.model.models import AccessToken


@pytest.fixture
def token_manager(config_manager):
    return TokenManager(config=config_manager)

@pytest.mark.asyncio
async def test_check_valid_token_lifetime(token_manager, mock_api_integration_response, mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is True


@pytest.mark.asyncio
async def test_check_invalid_token_lifetime(token_manager, mock_api_integration_response, mock_env_vars):
    client_id = "nonexistent-client-id"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_short_lifetime(token_manager, mock_lifetime_response, mock_env_vars):
    client_id = "short-lived-client-id"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_lifetime_response,
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_key_error(token_manager, mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload={"incorrect": "response"},
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_api_error(token_manager, mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            status=500,
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_empty_response(token_manager, mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload={},
            headers={"Accept": "application/json"},
        )
        result = await token_manager.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_fetch_token_invalid_response(token_manager, mock_env_vars):
    with aioresponses() as m:
        m.post(
            "https://mocked.url/api/oauth/token",
            payload={"invalid": "response"},
            status=200,
        )
        token = await token_manager.fetch_token()
        assert token is None


def test_token_valid_true(token_manager):
    # Make future_time timezone-aware by specifying tzinfo
    future_time = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(hours=1)
    token_manager.token = AccessToken(token="dummy_token", expires=future_time)
    assert token_manager.token_valid() is True


def test_token_valid_false(token_manager):
    # Make past_time timezone-aware by specifying tzinfo
    past_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=1)
    token_manager.token = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token_valid() is False


def test_token_valid_no_expiration(token_manager):
    past_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
    token_manager.token = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token_valid() is False
