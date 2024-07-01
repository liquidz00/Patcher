from datetime import datetime, timezone, timedelta
from unittest.mock import patch, call, ANY, MagicMock
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher.client.token_manager import TokenManager
from src.Patcher.model.models import AccessToken


@patch.object(ConfigManager, "set_credential")
def test_update_env(mock_set_credential, config_manager):
    token_manager = TokenManager(config=config_manager)
    token = "newToken"
    expires_in = 3600
    token_manager.update_token(token_str=token, expires_in=expires_in)

    expected_calls = [
        call("TOKEN", token),
        call("TOKEN_EXPIRATION", ANY),
    ]
    mock_set_credential.assert_has_calls(calls=expected_calls, any_order=True)
    assert mock_set_credential.call_count == 2


@patch.object(TokenManager, "check_token_lifetime", return_value=False)
def test_check_short_lifetime(mock_lifetime_response, short_lived_jamf_client):
    config = MagicMock(return_value=short_lived_jamf_client)
    token_manager = TokenManager(config=config)
    result = token_manager.check_token_lifetime(client=short_lived_jamf_client)
    assert result is False
    assert token_manager.token_valid() is False


@patch.object(ConfigManager, "get_credential")
def test_get_credentials(mock_get_credential, config_manager):
    def side_effect(key):
        if key == "CLIENT_ID":
            return "mocked_client_id"
        elif key == "CLIENT_SECRET":
            return "mocked_client_secret"
        return None

    mock_get_credential.side_effect = side_effect

    token_manager = TokenManager(config=config_manager)
    client_id, client_secret = token_manager.get_credentials()
    assert client_id == "mocked_client_id"
    assert client_secret == "mocked_client_secret"


def test_token_manager_initialization(config_manager):
    token_manager = TokenManager(config=config_manager)
    assert token_manager.token.token == "mocked_token"
    assert token_manager.token.expires == datetime(2030, 1, 1, tzinfo=timezone.utc)


@patch.object(ConfigManager, "set_credential")
def test_save_token(mock_set_credential, config_manager):
    token_manager = TokenManager(config=config_manager)
    token = AccessToken(
        token="new_token", expires=datetime(2031, 1, 1, tzinfo=timezone.utc)
    )
    token_manager.save_token(token)

    expected_calls = [
        call("TOKEN", "new_token"),
        call("TOKEN_EXPIRATION", token.expires.isoformat()),
    ]
    mock_set_credential.assert_has_calls(expected_calls, any_order=True)


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
