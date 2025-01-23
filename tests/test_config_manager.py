from unittest.mock import patch

import pytest
from keyring.errors import KeyringError
from src.patcher.client.config_manager import ConfigManager
from src.patcher.utils.exceptions import CredentialError


@pytest.fixture
def real_config_manager():
    return ConfigManager(service_name="TestService")


def test_get_credential_success(real_config_manager):
    with patch("keyring.get_password", return_value="mocked_credential") as mock_get_password:
        result = real_config_manager.get_credential("API_KEY")
        mock_get_password.assert_called_once_with("TestService", "API_KEY")
        assert result == "mocked_credential"


def test_get_credential_failure(real_config_manager):
    with patch("keyring.get_password", side_effect=KeyringError("Keyring failure")):
        with pytest.raises(CredentialError) as excinfo:
            real_config_manager.get_credential("API_KEY")
        assert "Unable to retrieve credential as expected" in str(excinfo.value)


def test_set_credential_success(real_config_manager):
    with patch("keyring.set_password") as mock_set_password:
        real_config_manager.set_credential("API_KEY", "mock_value")
        mock_set_password.assert_called_once_with("TestService", "API_KEY", "mock_value")


def test_set_credential_failure(real_config_manager):
    with patch("keyring.set_password", side_effect=KeyringError("Keyring failure")):
        with pytest.raises(CredentialError) as excinfo:
            real_config_manager.set_credential("API_KEY", "mock_value")
        assert "Unable to save credential as expected" in str(excinfo.value)


def test_delete_credential_success(real_config_manager):
    with patch("keyring.delete_password") as mock_delete_password:
        result = real_config_manager.delete_credential("API_KEY")
        mock_delete_password.assert_called_once_with("TestService", "API_KEY")
        assert result is True


def test_delete_credential_failure(real_config_manager):
    with patch("keyring.delete_password", side_effect=KeyringError("Keyring failure")):
        result = real_config_manager.delete_credential("API_KEY")
        assert result is False


def test_create_client_success(real_config_manager, mock_jamf_client, mock_access_token):
    with patch.object(real_config_manager, "set_credential") as mock_set_credential:
        real_config_manager.create_client(mock_jamf_client, mock_access_token)

        mock_set_credential.assert_any_call("CLIENT_ID", "mocked_client_id")
        mock_set_credential.assert_any_call("CLIENT_SECRET", "mocked_client_secret")
        mock_set_credential.assert_any_call("URL", "https://mocked.url")
        mock_set_credential.assert_any_call("TOKEN", "mocked_token")
        mock_set_credential.assert_any_call("TOKEN_EXPIRATION", str(mock_access_token.expires))
        assert mock_set_credential.call_count == 5


def test_reset_config_success(real_config_manager):
    with patch.object(
        real_config_manager, "delete_credential", return_value=True
    ) as mock_delete_credential:
        result = real_config_manager.reset_config()
        mock_delete_credential.assert_any_call("CLIENT_ID")
        mock_delete_credential.assert_any_call("CLIENT_SECRET")
        mock_delete_credential.assert_any_call("URL")
        mock_delete_credential.assert_any_call("TOKEN")
        mock_delete_credential.assert_any_call("TOKEN_EXPIRATION")
        assert mock_delete_credential.call_count == 5
        assert result is True


def test_reset_config_partial_failure(real_config_manager):
    delete_side_effects = [True, True, False, True, True]
    with patch.object(
        real_config_manager, "delete_credential", side_effect=delete_side_effects
    ) as mock_delete_credential:
        result = real_config_manager.reset_config()
        assert mock_delete_credential.call_count == 5
        assert result is False
