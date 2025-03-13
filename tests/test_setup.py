from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from src.patcher.client.setup import Setup, SetupType
from src.patcher.models.token import AccessToken
from src.patcher.utils.exceptions import SetupError


@pytest.fixture
def setup_instance(config_manager, ui_config, mock_plist_manager):
    instance = Setup(
        config=config_manager,
        ui_config=ui_config,
        plist_manager=mock_plist_manager,
    )
    instance.config.set_credential = MagicMock()
    instance.config.create_client = MagicMock()
    instance.plist_manager.remove = MagicMock()
    return instance


@pytest.mark.asyncio
async def test_init(setup_instance, config_manager, ui_config):
    assert setup_instance.config == config_manager
    assert setup_instance.ui_config == ui_config
    assert setup_instance._completed is None


def test_is_complete(setup_instance, mock_plist_manager):
    mock_plist_manager.get.return_value = True
    assert setup_instance.completed is True
    mock_plist_manager.get.assert_called_once_with("setup_completed")


def test_is_complete_error(setup_instance, mock_plist_manager):
    mock_plist_manager.get.side_effect = Exception("plist read error")

    with pytest.raises(Exception, match="plist read error"):
        # noinspection PyStatementEffect
        setup_instance.completed


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


def test_mark_completion(setup_instance, mock_plist_manager):
    setup_instance._mark_completion(value=True)
    mock_plist_manager.set.assert_called_once_with("setup_completed", True)


def test_reset_setup(setup_instance, mock_plist_manager):
    mock_plist_manager.remove.return_value = True
    assert setup_instance.reset_setup() is True
    mock_plist_manager.remove.assert_called_once_with("setup_completed")


@pytest.mark.asyncio
async def test_run_setup_standard(setup_instance):
    mock_token = AccessToken(token="mock_token", expires=datetime(2028, 1, 1, tzinfo=timezone.utc))
    with (
        patch("asyncclick.prompt", side_effect=["https://example.com", "user", "pass"]),
        patch("asyncclick.confirm", return_value=False),
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
        patch("asyncclick.confirm", return_value=False),
        patch.object(setup_instance, "_token_fetching", return_value=mock_token),
        patch.object(setup_instance, "_save_creds"),
        patch.object(setup_instance, "_mark_completion"),
        patch.object(setup_instance.animator, "update_msg"),
        patch.object(setup_instance.animator.stop_event, "set"),
    ):
        await setup_instance._run_setup(SetupType.SSO)
        setup_instance._save_creds.assert_called_once()
        setup_instance._mark_completion.assert_called_once_with(value=True)
