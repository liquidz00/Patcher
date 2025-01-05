import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from plistlib import InvalidFileException
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from src.patcher.client.setup import Setup, SetupType
from src.patcher.models.token import AccessToken
from src.patcher.utils.exceptions import SetupError


@pytest.fixture
def setup_instance(
    config_manager, ui_config, mock_jamf_client, api_client, token_manager, request, base_api_client
):
    # Create temp file path
    temp_plist = tempfile.NamedTemporaryFile(suffix=".plist", delete=False)
    temp_plist_path = Path(temp_plist.name)
    temp_plist.close()

    # Mock plist_path to use temp file
    with patch.object(ui_config, "plist_path", new=temp_plist_path):
        instance = Setup(
            config=config_manager,
            ui_config=ui_config,
        )
        instance.config.set_credential = MagicMock()
        instance.config.create_client = MagicMock()
        instance.animator.stop_event.set = AsyncMock()

        # Clean up after test
        def cleanup():
            if temp_plist_path.exists():
                os.remove(temp_plist_path)

        request.addfinalizer(cleanup)

        yield instance


@pytest.mark.asyncio
async def test_init(setup_instance, config_manager, ui_config):
    assert setup_instance.config == config_manager
    assert setup_instance.ui_config == ui_config
    assert setup_instance.ui_config.plist_path.exists()
    assert setup_instance._completed is None


def test_is_complete(setup_instance):
    with (
        patch.object(Path, "exists", return_value=True),
        patch("plistlib.load", return_value={"Setup": {"first_run_done": True}}),
        patch("builtins.open", mock_open(read_data=b"")),
    ):
        result = setup_instance._check_completion()
        assert result is True


def test_is_complete_error(setup_instance):
    with patch.object(Path, "exists", return_value=True):
        with patch("plistlib.load", side_effect=InvalidFileException("plist read error")):
            result = setup_instance._check_completion()
            assert result is False


def test_setup_type_enum():
    assert SetupType.STANDARD.value == "standard"
    assert SetupType.SSO.value == "sso"


def test_prompt_credentials_standard(setup_instance):
    with patch("asyncclick.prompt") as mock_prompt:
        mock_prompt.side_effect = ["https://example.com", "username", "password"]
        creds = setup_instance._prompt_credentials(SetupType.STANDARD)
        assert creds == {
            "URL": "https://example.com",
            "USERNAME": "username",
            "PASSWORD": "password",
        }


def test_prompt_credentials_sso(setup_instance):
    with patch("asyncclick.prompt") as mock_prompt:
        mock_prompt.side_effect = ["https://example.com", "client_id", "client_secret"]
        creds = setup_instance._prompt_credentials(SetupType.SSO)
        assert creds == {
            "URL": "https://example.com",
            "CLIENT_ID": "client_id",
            "CLIENT_SECRET": "client_secret",
        }


def test_validate_creds_success(setup_instance):
    creds = {"URL": "https://example.com", "USERNAME": "user", "PASSWORD": "pass"}
    setup_instance._validate_creds(creds, ("URL", "USERNAME", "PASSWORD"), SetupType.STANDARD)


def test_validate_creds_missing_keys(setup_instance):
    creds = {"URL": "https://example.com"}
    with pytest.raises(SetupError) as excinfo:
        setup_instance._validate_creds(creds, ("URL", "USERNAME", "PASSWORD"), SetupType.STANDARD)
    assert "Missing required credentials." in str(excinfo.value)


def test_save_creds(setup_instance):
    creds = {"URL": "https://example.com", "USERNAME": "user", "PASSWORD": "pass"}
    setup_instance._save_creds(creds)
    setup_instance.config.set_credential.assert_any_call("URL", "https://example.com")
    setup_instance.config.set_credential.assert_any_call("USERNAME", "user")
    setup_instance.config.set_credential.assert_any_call("PASSWORD", "pass")


def test_mark_completion(setup_instance):
    with (
        patch("os.makedirs", MagicMock()),
        patch("builtins.open", mock_open()) as mock_file,
        patch("plistlib.dump") as mock_dump,
    ):
        setup_instance._mark_completion(value=True)
        mock_file.assert_called_once_with(setup_instance.plist_path, "wb")
        mock_dump.assert_called_once()


@pytest.mark.asyncio
async def test_run_setup_standard(setup_instance):
    mock_token = AccessToken(token="mock_token", expires=datetime(2028, 1, 1, tzinfo=timezone.utc))
    with (
        patch("asyncclick.prompt", side_effect=["https://example.com", "user", "pass"]),
        patch.object(setup_instance, "_token_fetching", return_value=mock_token),
        patch.object(
            setup_instance, "_configure_integration", return_value=("client_id", "client_secret")
        ),
        patch.object(setup_instance, "_save_creds"),
        patch.object(setup_instance, "_mark_completion"),
        patch.object(setup_instance.animator, "update_msg"),
        patch.object(setup_instance.animator.stop_event, "set"),
    ):
        await setup_instance._run_setup(SetupType.STANDARD)
        setup_instance._save_creds.assert_called_once()
        setup_instance._mark_completion.assert_called_once_with(value=True)


@pytest.mark.asyncio
async def test_run_setup_sso(setup_instance):
    mock_token = AccessToken(token="mock_token", expires=datetime(2028, 1, 1, tzinfo=timezone.utc))
    with (
        patch(
            "asyncclick.prompt", side_effect=["https://example.com", "client_id", "client_secret"]
        ),
        patch.object(setup_instance, "_token_fetching", return_value=mock_token),
        patch.object(setup_instance, "_save_creds"),
        patch.object(setup_instance, "_mark_completion"),
        patch.object(setup_instance.animator, "update_msg"),
        patch.object(setup_instance.animator.stop_event, "set"),
    ):
        await setup_instance._run_setup(SetupType.SSO)
        setup_instance._save_creds.assert_called_once()
        setup_instance._mark_completion.assert_called_once_with(value=True)
