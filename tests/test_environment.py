import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from aiohttp import ClientResponseError
from src.patcher.client.config_manager import ConfigManager
from src.patcher.client.token_manager import TokenManager
from src.patcher.models.token import AccessToken
from src.patcher.utils.exceptions import TokenFetchError, TokenLifetimeError


@patch.object(TokenManager, "_check_token_lifetime", return_value=False)
def test_check_short_lifetime(mock_lifetime_response, short_lived_jamf_client):
    config = MagicMock(return_value=short_lived_jamf_client)
    token_manager = TokenManager(config=config)
    result = token_manager._check_token_lifetime()
    assert result is False
    assert token_manager.token_valid() is False


def test_token_manager_initialization(config_manager):
    token_manager = TokenManager(config=config_manager)
    assert token_manager.token.token == "mocked_token"
    assert token_manager.token.expires == datetime(2030, 1, 1, tzinfo=timezone.utc)


@patch.object(ConfigManager, "set_credential")
def test_save_token(mock_set_credential, config_manager):
    token_manager = TokenManager(config=config_manager)
    token = AccessToken(token="new_token", expires=datetime(2031, 1, 1, tzinfo=timezone.utc))
    token_manager._save_token(token)

    expected_calls = [
        call("TOKEN", "new_token"),
        call("TOKEN_EXPIRATION", token.expires.isoformat()),
    ]
    mock_set_credential.assert_has_calls(expected_calls, any_order=True)


def test_token_valid_true(token_manager):
    # Make future_time timezone-aware by specifying tzinfo
    future_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) + timedelta(hours=1)
    token_manager.token = AccessToken(token="dummy_token", expires=future_time)
    assert token_manager.token_valid() is True


def test_token_valid_false(token_manager):
    # Make past_time timezone-aware by specifying tzinfo
    past_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) - timedelta(hours=1)
    token_manager.token = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token_valid() is False


def test_token_valid_no_expiration(token_manager):
    past_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
    token_manager.token = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token_valid() is False


# Test token fetching
@pytest.mark.asyncio
async def test_fetch_token_success(token_manager, mock_jamf_client):
    # Mock the JSON response and the _parse_token_response method
    mock_response_json = {"access_token": "some_token", "expires_in": 3600}
    mock_parsed_token = AccessToken(
        token="some_token", expires=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )

    # Replace the mocked fetch_token with the real one
    token_manager.fetch_token = TokenManager.fetch_token.__get__(token_manager, TokenManager)

    with (
        patch("aiohttp.ClientSession.post") as mock_post,
        patch.object(
            TokenManager, "_parse_token_response", return_value=mock_parsed_token
        ) as mock_parse,
    ):
        # Mock the response of the post request
        mock_post.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_response_json
        )
        mock_post.return_value.__aenter__.return_value.raise_for_status = AsyncMock()

        # Call the real fetch_token method
        token = await token_manager.fetch_token()

        # Assert that _parse_token_response was called with the expected JSON response
        mock_parse.assert_called_once_with(mock_response_json)
        # Assert that the returned token is as expected
        assert token == mock_parsed_token


@pytest.mark.asyncio
async def test_fetch_token_client_response_error(token_manager, mock_jamf_client):
    # Replace mocked fetch_token with the real one
    token_manager.fetch_token = TokenManager.fetch_token.__get__(token_manager, TokenManager)

    with patch("aiohttp.ClientSession.post") as mock_post:
        # Simulate ClientResponseError being raised
        mock_post.return_value.__aenter__.return_value.raise_for_status.side_effect = (
            ClientResponseError(request_info=None, history=None)
        )

        token = await token_manager.fetch_token()

        # Assert that None is returned when ClientResponseError is thrown
        assert token is None


@pytest.mark.asyncio
async def test_fetch_token_value_error(token_manager, mock_jamf_client):
    # Replace the mocked fetch_token with the real one
    token_manager.fetch_token = TokenManager.fetch_token.__get__(token_manager, TokenManager)

    with patch("aiohttp.ClientSession.post") as mock_post:
        # Simulate a ValueError being raised during JSON parsing
        mock_post.return_value.__aenter__.return_value.json.side_effect = ValueError()

        # Call the real fetch_token method
        token = await token_manager.fetch_token()

        # Assert that None is returned when there is a ValueError
        assert token is None


# Test validity
@pytest.mark.asyncio
async def test_ensure_valid_token_valid_token(token_manager):
    # Mock token_valid to return True
    token_manager.token_valid = MagicMock(return_value=True)
    token_manager._check_token_lifetime = MagicMock(return_value=True)

    await token_manager.ensure_valid_token()

    # Ensure fetch_token is not called because the token is valid
    token_manager.fetch_token.assert_not_called()
    token_manager._check_token_lifetime.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_valid_token_invalid_token_fetch_success(token_manager):
    # Mock token_valid to return False, meaning the token is invalid
    token_manager.token_valid = MagicMock(return_value=False)
    # Mock fetch_token to return a new token successfully
    token_manager.fetch_token = AsyncMock(return_value=True)
    token_manager._check_token_lifetime = MagicMock(return_value=True)

    await token_manager.ensure_valid_token()

    # Ensure that fetch_token is called because the token was invalid
    token_manager.fetch_token.assert_called_once()
    token_manager._check_token_lifetime.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_valid_token_invalid_token_fetch_failure(token_manager):
    # Mock token_valid to return False, meaning the token is invalid
    token_manager.token_valid = MagicMock(return_value=False)
    # Mock fetch_token to simulate failure (returns False)
    token_manager.fetch_token = AsyncMock(return_value=False)

    with pytest.raises(TokenFetchError):
        await token_manager.ensure_valid_token()

    # Ensure that fetch_token is called
    token_manager.fetch_token.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_valid_token_token_lifetime_error(token_manager):
    # Mock token_valid to return True, meaning the token is valid
    token_manager.token_valid = MagicMock(return_value=True)
    # Mock _check_token_lifetime to return False, triggering a TokenLifetimeError
    token_manager._check_token_lifetime = MagicMock(return_value=False)

    with pytest.raises(TokenLifetimeError):
        await token_manager.ensure_valid_token()

    # Ensure that fetch_token is not called since the token is initially valid
    token_manager.fetch_token.assert_not_called()
    token_manager._check_token_lifetime.assert_called_once()


# Token Lifetime Checks
@pytest.mark.parametrize(
    "lifetime, expected_result",
    [
        (600, True),  # Token lifetime is between 5-10 minutes, sufficient
        (300, True),  # Token lifetime is exactly 5 minutes, sufficient
        (59, True),  # Token lifetime is less than 1 minute, but not zero
        (0, False),  # Token lifetime is zero, invalid
        (-1, False),  # Token lifetime is negative, invalid
    ],
)
def test_check_token_lifetime(token_manager, lifetime, expected_result):
    token_manager._check_token_lifetime = TokenManager._check_token_lifetime.__get__(
        token_manager, TokenManager
    )
    # Mock the token to have the specific lifetime
    token_manager.token = MagicMock()
    token_manager.token.seconds_remaining = lifetime

    result = token_manager._check_token_lifetime()

    # Assert that the result matches the expected result
    assert result == expected_result
