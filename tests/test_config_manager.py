from unittest.mock import patch

import pytest
from keyring.errors import KeyringError
from src.patcher.core.config_manager import ConfigManager
from src.patcher.core.exceptions import CredentialError


@pytest.fixture
def real_config_manager():
    return ConfigManager(service_name="TestService")


class TestGetCredential:
    def test_get_credential_success(self, real_config_manager):
        with patch("keyring.get_password", return_value="mocked_credential") as mock_get_password:
            result = real_config_manager.get_credential("API_KEY")
            mock_get_password.assert_called_once_with("TestService", "API_KEY")
            assert result == "mocked_credential"

    def test_get_credential_failure(self, real_config_manager):
        with patch("keyring.get_password", side_effect=KeyringError("Keyring failure")):
            with pytest.raises(CredentialError) as excinfo:
                real_config_manager.get_credential("API_KEY")
            assert "Unable to retrieve credential as expected" in str(excinfo.value)


class TestSetCredential:
    def test_set_credential_success(self, real_config_manager):
        with patch("keyring.set_password") as mock_set_password:
            real_config_manager.set_credential("API_KEY", "mock_value")
            mock_set_password.assert_called_once_with("TestService", "API_KEY", "mock_value")

    def test_set_credential_failure(self, real_config_manager):
        with patch("keyring.set_password", side_effect=KeyringError("Keyring failure")):
            with pytest.raises(CredentialError) as excinfo:
                real_config_manager.set_credential("API_KEY", "mock_value")
            assert "Unable to save credential as expected" in str(excinfo.value)

    def test_set_credential_raises_owner_mismatch_on_acl_error(self, real_config_manager):
        """
        Regression for #68: macOS Keychain ``-25244`` / ``errSecInvalidOwnerEdit``
        (fires when a different Python interpreter tries to update an existing
        item) must surface as a ``CredentialError`` with ``owner_mismatch=True``
        and an actionable recovery message. Otherwise the user just sees the raw
        macOS error code in a traceback with no path forward.
        """
        error = KeyringError("Can't store password on keychain: (-25244, 'Unknown Error')")
        with patch("keyring.set_password", side_effect=error):
            with pytest.raises(CredentialError) as excinfo:
                real_config_manager.set_credential("TOKEN", "x")

        err = excinfo.value
        assert getattr(err, "owner_mismatch", False) is True
        # The recovery instructions are the point of the special case; missing
        # them defeats the fix.
        assert "security delete-generic-password" in str(err)
        assert "--fresh" in str(err)

    def test_set_credential_keeps_generic_error_for_unrelated_keyring_failure(
        self, real_config_manager
    ):
        """Non-ACL ``KeyringError`` keeps the generic message and does not set ``owner_mismatch``."""
        with patch("keyring.set_password", side_effect=KeyringError("Keyring locked")):
            with pytest.raises(CredentialError) as excinfo:
                real_config_manager.set_credential("API_KEY", "v")
        err = excinfo.value
        assert getattr(err, "owner_mismatch", False) is False
        assert "Unable to save credential as expected" in str(err)


class TestDeleteCredential:
    def test_delete_credential_success(self, real_config_manager):
        with patch("keyring.delete_password") as mock_delete_password:
            result = real_config_manager.delete_credential("API_KEY")
            mock_delete_password.assert_called_once_with("TestService", "API_KEY")
            assert result is True

    def test_delete_credential_failure(self, real_config_manager):
        # Best-effort by design: a present-but-undeletable credential still reports True
        # because it's overwritten at the next setup (a broken keyring fails at write time).
        with patch("keyring.delete_password", side_effect=KeyringError("Keyring failure")):
            result = real_config_manager.delete_credential("API_KEY")
            assert result is True


class TestCreateClient:
    def test_create_client_success(
        self, real_config_manager, mock_jamf_credentials, mock_access_token
    ):
        with patch.object(real_config_manager, "set_credential") as mock_set_credential:
            real_config_manager.create_client(mock_jamf_credentials, mock_access_token)

            mock_set_credential.assert_any_call("CLIENT_ID", "mocked_client_id")
            mock_set_credential.assert_any_call("CLIENT_SECRET", "mocked_client_secret")
            mock_set_credential.assert_any_call("URL", "https://mocked.url")
            mock_set_credential.assert_any_call("TOKEN", "mocked_token")
            mock_set_credential.assert_any_call("TOKEN_EXPIRATION", str(mock_access_token.expires))
            assert mock_set_credential.call_count == 5


class TestResetConfig:
    def test_reset_config_success(self, real_config_manager):
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

    def test_reset_config_partial_failure(self, real_config_manager):
        delete_side_effects = [True, True, False, True, True]
        with patch.object(
            real_config_manager, "delete_credential", side_effect=delete_side_effects
        ) as mock_delete_credential:
            result = real_config_manager.reset_config()
            assert mock_delete_credential.call_count == 5
            assert result is False


# In-memory mode (non-interactive / CI/CD)


class TestInMemoryMode:
    def test_in_memory_mode_property(self):
        """A ConfigManager constructed with in_memory_credentials reports in_memory_mode=True."""
        cm_keychain = ConfigManager(service_name="TestService")
        cm_memory = ConfigManager(service_name="TestService", in_memory_credentials={})

        assert cm_keychain.in_memory_mode is False
        assert cm_memory.in_memory_mode is True

    def test_in_memory_get_returns_from_dict_without_keyring(self):
        """get_credential reads from the in-memory dict and never touches keyring."""
        cm = ConfigManager(
            service_name="TestService",
            in_memory_credentials={"CLIENT_ID": "abc-123"},
        )
        with patch("keyring.get_password") as mock_keyring:
            result = cm.get_credential("CLIENT_ID")
        assert result == "abc-123"
        mock_keyring.assert_not_called()

    def test_in_memory_get_returns_none_for_missing_key(self):
        """get_credential returns None for absent keys without raising."""
        cm = ConfigManager(service_name="TestService", in_memory_credentials={})
        with patch("keyring.get_password") as mock_keyring:
            assert cm.get_credential("NEVER_SET") is None
        mock_keyring.assert_not_called()

    def test_in_memory_set_writes_to_dict_without_keyring(self):
        """set_credential writes to the in-memory dict and never touches keyring."""
        cm = ConfigManager(service_name="TestService", in_memory_credentials={})
        with patch("keyring.set_password") as mock_keyring:
            cm.set_credential("CLIENT_SECRET", "shh")
        assert cm.get_credential("CLIENT_SECRET") == "shh"
        mock_keyring.assert_not_called()

    def test_in_memory_delete_removes_from_dict_without_keyring(self):
        """delete_credential pops from the in-memory dict and never touches keyring."""
        cm = ConfigManager(service_name="TestService", in_memory_credentials={"TOKEN": "abc"})
        with patch("keyring.delete_password") as mock_keyring:
            assert cm.delete_credential("TOKEN") is True
        assert cm.get_credential("TOKEN") is None
        mock_keyring.assert_not_called()

    def test_in_memory_constructor_copies_input_dict(self):
        """Mutating the dict passed in shouldn't leak into the ConfigManager."""
        creds = {"URL": "https://example.com"}
        cm = ConfigManager(service_name="TestService", in_memory_credentials=creds)
        creds["URL"] = "https://changed.example.com"
        assert cm.get_credential("URL") == "https://example.com"
