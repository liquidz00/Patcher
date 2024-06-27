import pytest
from datetime import datetime, timezone
from unittest.mock import patch, call, ANY
from src.client.config_manager import ConfigManager
from src.client.token_manager import TokenManager
from src.model.models import AccessToken


@pytest.fixture
def mock_config_manager():
    with (
        patch("src.client.config_manager.keyring.get_password") as mock_get_password,
        patch("src.client.config_manager.keyring.set_password") as mock_set_password,
    ):

        def side_effect(service_name, key):
            if key == "TOKEN":
                return "mocked_token"
            elif key == "TOKEN_EXPIRATION":
                return datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
            elif key == "URL":
                return "https://mocked.url"
            elif key == "CLIENT_ID":
                return "mocked_client_id"
            elif key == "CLIENT_SECRET":
                return "mocked_client_secret"
            return None

        mock_get_password.side_effect = side_effect
        config_manager = ConfigManager(service_name="patcher")
        yield config_manager


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


def test_config_manager_initialization(mock_config_manager):
    assert mock_config_manager.get_credential("TOKEN") == "mocked_token"
    assert (
        mock_config_manager.get_credential("TOKEN_EXPIRATION")
        == datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    )


@patch.object(ConfigManager, "get_credential")
def test_get_credentials(mock_get_credential, mock_config_manager):
    def side_effect(key):
        if key == "CLIENT_ID":
            return "mocked_client_id"
        elif key == "CLIENT_SECRET":
            return "mocked_client_secret"
        return None

    mock_get_credential.side_effect = side_effect

    token_manager = TokenManager(config=mock_config_manager)
    client_id, client_secret = token_manager.get_credentials()
    assert client_id == "mocked_client_id"
    assert client_secret == "mocked_client_secret"


def test_token_manager_initialization(mock_config_manager):
    token_manager = TokenManager(config=mock_config_manager)
    assert token_manager.token.token == "mocked_token"
    assert token_manager.token.expires == datetime(2030, 1, 1, tzinfo=timezone.utc)


@patch.object(ConfigManager, "set_credential")
def test_save_token(mock_set_credential, mock_config_manager):
    token_manager = TokenManager(config=mock_config_manager)
    token = AccessToken(
        token="new_token", expires=datetime(2031, 1, 1, tzinfo=timezone.utc)
    )
    token_manager.save_token(token)

    expected_calls = [
        call("TOKEN", "new_token"),
        call("TOKEN_EXPIRATION", token.expires.isoformat()),
    ]
    mock_set_credential.assert_has_calls(expected_calls, any_order=True)
