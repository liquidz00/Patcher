import pytest

from aioresponses import aioresponses
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from bin import utils

from conftest import jamf_url, headers


@pytest.mark.asyncio
async def test_check_valid_token_lifetime(mock_api_integration_response, mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is True


@pytest.mark.asyncio
async def test_check_invalid_token_lifetime(mock_api_integration_response, mock_env_vars):
    client_id = "nonexistent-client-id"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_short_lifetime(mock_lifetime_response, mock_env_vars):
    client_id = "short-lived-client-id"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            payload=mock_lifetime_response,
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_key_error(mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            payload={"incorrect": "response"},
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_api_error(mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            status=500,
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_check_token_lifetime_empty_response(mock_env_vars):
    client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v1/api-integrations",
            payload={},
            headers=headers,
        )
        result = await utils.check_token_lifetime(client_id=client_id)
        assert result is False


@pytest.mark.asyncio
async def test_fetch_token_invalid_response(mock_env_vars):
    with aioresponses() as m:
        m.post(
            f"{jamf_url}/api/oauth/token",
            payload={"invalid": "response"},
            status=200,
        )
        token = await utils.fetch_token()
        assert token is None


def test_token_valid_true():
    # Make future_time timezone-aware by specifying tzinfo
    future_time = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(hours=1)
    with patch("os.getenv", return_value=str(future_time.timestamp())):
        assert utils.token_valid() is True


def test_token_valid_false():
    # Make past_time timezone-aware by specifying tzinfo
    past_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=1)
    with patch("os.getenv", return_value=str(past_time.timestamp())):
        assert utils.token_valid() is False


def test_token_valid_no_expiration():
    with patch("os.getenv", return_value=None):
        assert utils.token_valid() is False
