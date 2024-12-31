from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

import pytest
from src.patcher.client.config_manager import ConfigManager
from src.patcher.client.token_manager import TokenManager
from src.patcher.models.token import AccessToken
from src.patcher.utils.exceptions import TokenError


@patch.object(TokenManager, "token", new_callable=PropertyMock)
def test_token_manager_initialization(mock_token, config_manager):
    mock_token.return_value = AccessToken(
        token="mocked_token", expires=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )
    token_manager = TokenManager(config=config_manager)
    assert token_manager.token.token == "mocked_token"
    assert token_manager.token.expires == datetime(2030, 1, 1, tzinfo=timezone.utc)


@patch.object(ConfigManager, "set_credential", new_callable=MagicMock)
def test_save_token(mock_set_credential):
    mock_config_manager = MagicMock()

    mock_config_manager.set_credential = mock_set_credential

    token_manager = TokenManager(config=mock_config_manager)
    token = AccessToken(token="new_token", expires=datetime(2031, 1, 1, tzinfo=timezone.utc))

    token_manager._save_token(token)

    expected_calls = [
        call("TOKEN", "new_token"),
        call("TOKEN_EXPIRATION", token.expires.isoformat()),
    ]
    mock_set_credential.assert_has_calls(expected_calls, any_order=True)


@patch.object(TokenManager, "token", new_callable=PropertyMock)
def test_token_valid_true(mock_token, token_manager):
    # Make future_time timezone-aware by specifying tzinfo
    future_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) + timedelta(hours=1)
    mock_token.return_value = AccessToken(token="dummy_token", expires=future_time)
    assert token_manager.token.is_expired is False


@patch.object(TokenManager, "token", new_callable=PropertyMock)
def test_token_valid_false(mock_token, token_manager):
    # Make past_time timezone-aware by specifying tzinfo
    past_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc) - timedelta(hours=1)
    mock_token.return_value = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token.is_expired is True


@patch.object(TokenManager, "token", new_callable=PropertyMock)
def test_token_valid_no_expiration(mock_token, token_manager):
    past_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
    mock_token.return_value = AccessToken(token="dummy_token", expires=past_time)
    assert token_manager.token.is_expired is True


# Test validity
@pytest.mark.asyncio
@patch.object(AccessToken, "is_expired", new_callable=PropertyMock)
async def test_ensure_valid_token_valid_token(mock_is_expired, token_manager):
    token_manager.fetch_token = AsyncMock()

    # Mock token_valid to return True
    mock_is_expired.return_value = False

    await token_manager.ensure_valid_token()

    # Ensure fetch_token is not called because the token is valid
    token_manager.fetch_token.assert_not_called()


@pytest.mark.asyncio
@patch.object(TokenManager, "token", new_callable=PropertyMock)
async def test_ensure_valid_token_invalid_token_fetch_success(mock_token, token_manager):
    mock_token.return_value = AccessToken(
        token="expired_token", expires=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    # Mock token_valid to return False, meaning the token is invalid
    token_manager.token_valid = MagicMock(return_value=False)
    # Mock fetch_token to return a new token successfully
    token_manager.fetch_token = AsyncMock(return_value=True)

    await token_manager.ensure_valid_token()

    # Ensure that fetch_token is called because the token was invalid
    token_manager.fetch_token.assert_called_once()


@pytest.mark.asyncio
@patch.object(TokenManager, "token", new_callable=PropertyMock)
async def test_ensure_valid_token_invalid_token_fetch_failure(mock_token, token_manager):
    mock_token.return_value = AccessToken(
        token="expired_token", expires=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    # Mock token_valid to return False, meaning the token is invalid
    token_manager.token_valid = MagicMock(return_value=False)

    # Mock fetch_token to raise TokenError
    token_manager.fetch_token = AsyncMock(side_effect=TokenError("Unable to retrieve token"))

    with pytest.raises(TokenError, match="Unable to retrieve token"):
        await token_manager.ensure_valid_token()

    # Ensure that fetch_token is called
    token_manager.fetch_token.assert_called_once()
