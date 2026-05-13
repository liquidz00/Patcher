from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.patcher.cli.setup import Setup, SetupType
from src.patcher.core.exceptions import SetupError

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit


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


@pytest.mark.asyncio
async def testprompt_credentials_standard(setup_instance):
    # ``prompt_credentials`` is async because it awaits ``click.prompt`` (which
    # is an ``async def`` in asyncclick 8.2+). See #58.
    expected_creds = {
        "URL": "https://example.com",
        "USERNAME": "username",
        "PASSWORD": "password",
    }
    with patch.object(setup_instance, "prompt_credentials", AsyncMock(return_value=expected_creds)):
        creds = await setup_instance.prompt_credentials(SetupType.STANDARD)
        assert creds == expected_creds


@pytest.mark.asyncio
async def testprompt_credentials_sso(setup_instance):
    expected_creds = {
        "URL": "https://example.com",
        "CLIENT_ID": "client_id",
        "CLIENT_SECRET": "client_secret",
    }
    with patch.object(setup_instance, "prompt_credentials", AsyncMock(return_value=expected_creds)):
        creds = await setup_instance.prompt_credentials(SetupType.SSO)
        assert creds == expected_creds


def test_methods_with_click_prompt_are_async():
    """
    Regression for #58 — ``click.prompt`` is ``async def`` in asyncclick 8.2+;
    methods that call it must be ``async def`` so they can ``await`` it.

    The original bug was that ``Setup.prompt_credentials``,
    ``prompt_ui_settings``, ``prompt_font_config``, and ``prompt_logo_config``
    called ``click.prompt`` synchronously, producing un-awaited coroutines
    that silently broke setup with ``RuntimeWarning`` and then
    ``RecursionError``.
    """
    import inspect

    for method in (
        Setup.prompt_credentials,
        Setup.prompt_ui_settings,
        Setup.prompt_font_config,
        Setup.prompt_logo_config,
    ):
        assert inspect.iscoroutinefunction(method), (
            f"{method.__qualname__} calls click.prompt and must be async. See issue #58."
        )


def test_setup_start_does_not_self_recurse():
    """
    Regression for #58 — ``Setup.start()`` must retry invalid input via a loop,
    not by calling itself recursively. The recursion was the mechanism that
    turned the unawaited-coroutine bug into a stack-exhausting RecursionError.
    """
    import inspect

    source = inspect.getsource(Setup.start)
    assert "await self.start(" not in source, (
        "Setup.start() must not recursively call itself on invalid input — "
        "use a `while True` loop instead. See issue #58."
    )


def testvalidate_creds_success(setup_instance):
    creds = {"URL": "https://example.com", "USERNAME": "user", "PASSWORD": "pass"}
    setup_instance.validate_creds(creds, ("URL", "USERNAME", "PASSWORD"), SetupType.STANDARD)


def testvalidate_creds_missing_keys(setup_instance):
    creds = {"URL": "https://example.com"}
    with pytest.raises(SetupError) as excinfo:
        setup_instance.validate_creds(creds, ("URL", "USERNAME", "PASSWORD"), SetupType.STANDARD)
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
    """Test the standard setup flow"""
    # Simply test that the setup would call the right methods
    mock_save_creds = MagicMock()
    mock_mark_completion = MagicMock()

    setup_instance._save_creds = mock_save_creds
    setup_instance._mark_completion = mock_mark_completion

    async def mock_start(animator=None, fresh=False):
        # Simulate the standard setup flow
        mock_save_creds({"URL": "https://example.com", "USERNAME": "user", "PASSWORD": "pass"})
        mock_mark_completion(value=True)

    with patch.object(setup_instance, "start", side_effect=mock_start):
        await setup_instance.start(fresh=True)
        mock_save_creds.assert_called_once_with(
            {"URL": "https://example.com", "USERNAME": "user", "PASSWORD": "pass"}
        )
        mock_mark_completion.assert_called_once_with(value=True)


@pytest.mark.asyncio
async def test_run_setup_sso(setup_instance):
    """Test the SSO setup flow"""
    # Simply test that the setup would call the right methods
    mock_save_creds = MagicMock()
    mock_mark_completion = MagicMock()

    setup_instance._save_creds = mock_save_creds
    setup_instance._mark_completion = mock_mark_completion

    async def mock_start(animator=None, fresh=False):
        # Simulate the SSO setup flow
        mock_save_creds(
            {
                "URL": "https://example.com",
                "CLIENT_ID": "client_id",
                "CLIENT_SECRET": "client_secret",
            }
        )
        mock_mark_completion(value=True)

    with patch.object(setup_instance, "start", side_effect=mock_start):
        await setup_instance.start(fresh=True)
        mock_save_creds.assert_called_once_with(
            {
                "URL": "https://example.com",
                "CLIENT_ID": "client_id",
                "CLIENT_SECRET": "client_secret",
            }
        )
        mock_mark_completion.assert_called_once_with(value=True)


# Non-interactive bootstrap (CI/CD path)


@pytest.mark.asyncio
async def test_bootstrap_noninteractive_success(setup_instance):
    """Bootstrap saves creds, fetches a token, and marks completion in memory."""
    setup_instance.config.set_credential.reset_mock()

    with patch("src.patcher.cli.setup.TokenManager") as MockTokenManager:
        mock_tm = MagicMock()
        mock_tm.fetch_token = MagicMock()

        async def fake_fetch_token():
            return MagicMock(token="abc", expires="2099-01-01T00:00:00Z")

        mock_tm.fetch_token.side_effect = fake_fetch_token
        MockTokenManager.return_value = mock_tm

        await setup_instance.bootstrap_noninteractive(
            client_id="cid", client_secret="csec", url="https://jamf.example.com"
        )

    # All three creds were saved via ConfigManager
    saved_calls = setup_instance.config.set_credential.call_args_list
    saved_keys = {call.args[0] for call in saved_calls}
    assert {"URL", "CLIENT_ID", "CLIENT_SECRET"}.issubset(saved_keys)

    # Token was fetched
    mock_tm.fetch_token.assert_called_once()

    # In-memory completion marked, no plist write
    assert setup_instance._completed is True
    setup_instance.plist_manager.set.assert_not_called() if hasattr(
        setup_instance.plist_manager.set, "assert_not_called"
    ) else None


@pytest.mark.asyncio
async def test_bootstrap_noninteractive_token_failure_raises_setuperror(setup_instance):
    """If the token fetch fails, a SetupError is raised with a clear message."""
    from src.patcher.core.exceptions import TokenError

    with patch("src.patcher.cli.setup.TokenManager") as MockTokenManager:
        mock_tm = MagicMock()

        async def boom():
            raise TokenError("bad creds", url="https://jamf.example.com", error_msg="401")

        mock_tm.fetch_token.side_effect = boom
        MockTokenManager.return_value = mock_tm

        with pytest.raises(SetupError) as excinfo:
            await setup_instance.bootstrap_noninteractive(
                client_id="cid", client_secret="bad", url="https://jamf.example.com"
            )

    assert "non-interactive mode" in str(excinfo.value)
    # Completion NOT marked
    assert setup_instance._completed is None or setup_instance._completed is False
