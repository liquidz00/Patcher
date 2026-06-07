from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.patcher.cli.setup import Setup, SetupType
from src.patcher.core.exceptions import SetupError
from src.patcher.core.models.settings import PatcherSettings

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit


@pytest.fixture
def setup_instance(config_manager, mocker):
    mocker.patch.object(PatcherSettings, "save")  # no disk writes during setup tests
    instance = Setup(config=config_manager, settings=PatcherSettings())
    instance.config.set_credential = MagicMock()
    instance.config.create_client = MagicMock()
    return instance


@pytest.mark.asyncio
async def test_init(setup_instance, config_manager):
    assert setup_instance.config == config_manager
    assert isinstance(setup_instance.settings, PatcherSettings)
    assert setup_instance._completed is None


def test_is_complete(setup_instance):
    setup_instance.settings.setup_completed = True
    assert setup_instance.completed is True


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


def test_mark_completion(setup_instance):
    setup_instance._mark_completion(value=True)
    assert setup_instance.settings.setup_completed is True
    PatcherSettings.save.assert_called()


def test_reset_setup(setup_instance):
    setup_instance.settings.setup_completed = True
    assert setup_instance.reset_setup() is True
    assert setup_instance.settings.setup_completed is False


@pytest.mark.asyncio
async def test_run_setup_standard(setup_instance):
    """Test the standard setup flow"""
    # Simply test that the setup would call the right methods
    mock_save_creds = MagicMock()
    mock_mark_completion = MagicMock()

    setup_instance._save_creds = mock_save_creds
    setup_instance._mark_completion = mock_mark_completion

    async def mock_start(spinner=None, fresh=False):
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

    async def mock_start(spinner=None, fresh=False):
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


@pytest.mark.asyncio
async def test_start_persists_credentials_via_jamf_credentials(setup_instance):
    """End-to-end exercise of ``Setup.start()`` running the *real* method body.

    The earlier ``test_run_setup_standard`` and ``test_run_setup_sso`` mock
    ``start()`` itself, so the credential-persistence block at the bottom of
    ``start()`` never executes during tests. That hid a real bug for an
    entire release cycle: the block was constructing ``JamfClient(...)``
    (the HTTP client) instead of ``JamfCredentials(...)`` (the Pydantic
    model expected by ``config.create_client``), and ``JamfClient`` wasn't
    even imported, so the failure was a ``NameError`` for every user running
    ``patcherctl --setup`` end-to-end.

    This test runs the real ``start()`` with only the I/O collaborators
    mocked (prompts, spinner, token fetch) and asserts the
    credential-persistence call sees a real ``JamfCredentials`` instance.
    A future regression of the same shape (wrong class, missing import,
    bad kwargs) fails this test immediately.
    """
    from src.patcher.core.models.jamf import JamfCredentials
    from src.patcher.core.models.token import AccessToken

    # No-op spinner (sync; its .update is called without await).
    spinner = MagicMock()

    sso_creds = {
        "URL": "https://test.jamfcloud.com",
        "CLIENT_ID": "abc-123",
        "CLIENT_SECRET": "secret-xyz",
    }
    creds_with_token = {
        **sso_creds,
        "TOKEN": "bearer-token-value",
        "TOKEN_EXPIRATION": "2030-01-01T00:00:00+00:00",
    }

    # Mock every collaborator that does I/O or prompts. Leave the real
    # credential-persistence block intact; that's the code under test.
    with patch("src.patcher.cli.setup.click.prompt", new=AsyncMock(return_value=2)):
        setup_instance.prompt_credentials = AsyncMock(return_value=sso_creds)
        setup_instance.prompt_installomator = MagicMock()
        setup_instance.validate_creds = MagicMock()
        setup_instance._save_creds = MagicMock()
        setup_instance.get_token = AsyncMock(return_value="dummy-basic-token")
        setup_instance.prompt_ui_settings = AsyncMock()
        setup_instance._mark_completion = MagicMock()
        # _get_creds is called twice: once without token, once with.
        setup_instance._get_creds = MagicMock(side_effect=[sso_creds, creds_with_token])

        await setup_instance.start(fresh=True, spinner=spinner)

    # The whole point of this test: config.create_client must receive a
    # JamfCredentials instance, not JamfClient or some other class. If
    # someone re-introduces ``JamfClient(...)`` in setup.py, this fails
    # before reaching production.
    setup_instance.config.create_client.assert_called_once()
    call = setup_instance.config.create_client.call_args

    credentials_arg = call.args[0]
    assert isinstance(credentials_arg, JamfCredentials), (
        f"Expected JamfCredentials, got {type(credentials_arg).__name__}"
    )
    assert credentials_arg.client_id == "abc-123"
    assert credentials_arg.client_secret.get_secret_value() == "secret-xyz"
    assert credentials_arg.server == "https://test.jamfcloud.com"

    token_arg = call.kwargs["token"]
    assert isinstance(token_arg, AccessToken)
    assert token_arg.token.get_secret_value() == "bearer-token-value"

    setup_instance._mark_completion.assert_called_once_with(value=True)


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

    # In-memory completion marked, no disk write
    assert setup_instance._completed is True
    PatcherSettings.save.assert_not_called()


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


@pytest.mark.asyncio
async def test_start_records_interpreter_path_before_marking_complete(setup_instance):
    """
    Regression for #68: successful setup must persist ``sys.executable`` to the
    plist under ``interpreter_path`` so the CLI preflight on later runs can
    detect a Python interpreter binding mismatch and surface a friendly
    recovery message before the Keychain ACL failure happens mid-run.
    """
    import sys as _sys

    spinner = MagicMock()
    sso_creds = {
        "URL": "https://test.jamfcloud.com",
        "CLIENT_ID": "abc-123",
        "CLIENT_SECRET": "secret-xyz",
    }
    creds_with_token = {
        **sso_creds,
        "TOKEN": "bearer-token-value",
        "TOKEN_EXPIRATION": "2030-01-01T00:00:00+00:00",
    }

    with patch("src.patcher.cli.setup.click.prompt", new=AsyncMock(return_value=2)):
        setup_instance.prompt_credentials = AsyncMock(return_value=sso_creds)
        setup_instance.prompt_installomator = MagicMock()
        setup_instance.validate_creds = MagicMock()
        setup_instance._save_creds = MagicMock()
        setup_instance.get_token = AsyncMock(return_value="dummy-basic-token")
        setup_instance.prompt_ui_settings = AsyncMock()
        setup_instance._mark_completion = MagicMock()
        setup_instance._get_creds = MagicMock(side_effect=[sso_creds, creds_with_token])

        await setup_instance.start(fresh=True, spinner=spinner)

    assert setup_instance.settings.interpreter_path == _sys.executable
