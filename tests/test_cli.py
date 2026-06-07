"""
CLI tests for ``patcherctl`` (the asyncclick command group).

Two complementary techniques, since asyncclick + the standard Click test
runner don't play nicely:

1. **Direct callback** — call a command's underlying ``async def`` via
   ``cmd.callback.__wrapped__(ctx, ...)`` with a hand-built ``ctx.obj``.
   No Click/anyio machinery; ideal for the branchy command bodies.
2. **CliRunner** — ``asyncclick.testing.CliRunner`` driven through
   ``await runner.invoke(...)`` for true end-to-end coverage of arg parsing,
   ``Choice`` validation, prompts, exit codes, and the group callback.

FILE-SAFETY GUARANTEE
---------------------
The module-scoped autouse ``_no_disk`` fixture neutralizes every filesystem /
keychain / network entry point the CLI can reach: the real plist is never read
or written, the cache dir is never created, the setup wizard never runs, fonts
are never downloaded. No individual test has to remember. ``test_real_patcher_
dirs_untouched`` proves it by snapshotting the real directories before/after a
destructive command.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncclick.testing import CliRunner
from src.patcher.cli import cli, export, reset
from src.patcher.core.models.settings import PatcherSettings


@pytest.fixture(autouse=True)
def _no_disk(mocker):
    """Hard guarantee: nothing in this module touches real disk, keychain, or network."""
    # The real plist: never read, never written — no matter who calls load()/save().
    mocker.patch.object(PatcherSettings, "load", return_value=PatcherSettings(setup_completed=True))
    mocker.patch.object(PatcherSettings, "save")  # MagicMock — plist writes are swallowed
    # Cache-dir creation, file-log handlers, signal/excepthook installation.
    mocker.patch("src.patcher.cli.initialize_cache")
    mocker.patch("src.patcher.cli.setup_logging")
    mocker.patch("src.patcher.cli._install_cli_process_hooks")
    # Keychain.
    mocker.patch("src.patcher.cli.ConfigManager")
    # The setup wizard writes the plist + downloads fonts; the cache helper deletes files.
    mocker.patch("src.patcher.cli.Setup.start")  # async def → AsyncMock
    mocker.patch("src.patcher.cli.Setup.prompt_ui_settings")  # async def → AsyncMock
    mocker.patch("src.patcher.cli.get_data_manager")


def _ctx(**overrides):
    """A fake Click context with a mocked ``ctx.obj`` for direct-callback tests."""
    obj = {
        "log": MagicMock(),
        "config": MagicMock(),
        "setup": MagicMock(),
        "settings": PatcherSettings(setup_completed=True),
        "debug": True,  # status() collapses to a no-op spinner
        "disable_cache": True,  # skips get_data_manager
    }
    obj.update(overrides)
    ctx = MagicMock()
    ctx.obj = obj
    return ctx


# --------------------------------------------------------------------------
# Group + per-command smoke tests (CliRunner — arg parsing, exit codes)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_help():
    result = await CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


@pytest.mark.asyncio
async def test_group_version():
    result = await CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0


@pytest.mark.parametrize("command", ["reset", "export", "analyze", "diff", "drift"])
@pytest.mark.asyncio
async def test_command_help_smoke(command):
    """Each command is registered and its options parse (catches wiring regressions)."""
    result = await CliRunner().invoke(cli, ["-x", command, "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


@pytest.mark.asyncio
async def test_reset_invalid_kind_exits_2():
    """A bad Choice argument is rejected by Click with the usage-error exit code."""
    result = await CliRunner().invoke(cli, ["-x", "--disable-cache", "reset", "bogus"])
    assert result.exit_code == 2


@pytest.mark.asyncio
async def test_reset_creds_url_end_to_end():
    """Full runner path: group callback + arg parsing + interactive prompt + body."""
    result = await CliRunner().invoke(
        cli,
        ["-x", "--disable-cache", "reset", "creds", "-c", "url"],
        input="https://test.jamfcloud.com\n",
    )

    # ConfigManager is patched in the autouse fixture; the group built one instance.
    from src.patcher.cli import ConfigManager

    assert result.exit_code == 0, result.output
    ConfigManager.return_value.set_credential.assert_called_once_with(
        "URL", "https://test.jamfcloud.com"
    )


# --------------------------------------------------------------------------
# reset command bodies (direct callback)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_full_runs_every_step():
    config = MagicMock()
    config.reset_config.return_value = True
    setup = MagicMock()
    setup.reset_ui_config.return_value = True
    setup.reset_setup.return_value = True
    setup.start = AsyncMock()
    ctx = _ctx(config=config, setup=setup)

    await reset.callback.__wrapped__(ctx, kind="full", credential=None)

    config.reset_config.assert_called_once()
    setup.reset_ui_config.assert_called_once()
    setup.reset_setup.assert_called_once()
    setup.start.assert_awaited_once()  # "full" relaunches setup afterward


@pytest.mark.asyncio
async def test_reset_ui_reconfigures():
    setup = MagicMock()
    setup.reset_ui_config.return_value = True
    setup.prompt_ui_settings = AsyncMock()
    ctx = _ctx(setup=setup)

    await reset.callback.__wrapped__(ctx, kind="UI", credential=None)

    setup.reset_ui_config.assert_called_once()
    setup.prompt_ui_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_single_credential(mocker):
    mocker.patch(
        "src.patcher.cli.click.prompt", new=AsyncMock(return_value="https://x.jamfcloud.com")
    )
    config = MagicMock()
    ctx = _ctx(config=config)

    await reset.callback.__wrapped__(ctx, kind="creds", credential="url")

    config.set_credential.assert_called_once_with("URL", "https://x.jamfcloud.com")


@pytest.mark.asyncio
async def test_reset_cache_when_disabled_exits_cleanly():
    """With caching off there's no data_manager in ctx.obj, so reset cache no-ops out."""
    ctx = _ctx()  # disable_cache=True, no "data_manager" key

    with pytest.raises(SystemExit) as excinfo:
        await reset.callback.__wrapped__(ctx, kind="cache", credential=None)

    assert excinfo.value.code == 0


# --------------------------------------------------------------------------
# export command body (direct callback, PatcherClient mocked)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_threads_settings_into_client_and_runs(mocker):
    mock_client_cls = mocker.patch("src.patcher.cli.PatcherClient")
    mock_proc = mocker.patch("src.patcher.cli.process_reports", new_callable=AsyncMock)
    settings = PatcherSettings(enable_matching=True, ignored_titles=["Adobe *"])
    ctx = _ctx(settings=settings)

    await export.callback.__wrapped__(
        ctx,
        path="/tmp/does-not-matter",
        formats=(),
        sort=None,
        omit=False,
        date_format="Month-Day-Year",
        ios=False,
        concurrency=7,
        device_details=False,
        homebrew=False,
    )

    kwargs = mock_client_cls.call_args.kwargs
    assert kwargs["enable_installomator"] is True
    assert kwargs["ignored_titles"] == ["Adobe *"]
    assert kwargs["concurrency"] == 7
    assert kwargs["enable_homebrew"] is False
    mock_proc.assert_awaited_once()


# --------------------------------------------------------------------------
# Proof of file safety
# --------------------------------------------------------------------------


def _snapshot(directory: Path):
    """Name → mtime map for a directory's entries, or None if it doesn't exist."""
    if not directory.exists():
        return None
    return {p.name: p.stat().st_mtime_ns for p in directory.iterdir()}


@pytest.mark.asyncio
async def test_real_patcher_dirs_untouched_after_destructive_command():
    """Running a destructive command must not read-modify-write the real Patcher dirs."""
    support = Path.home() / "Library/Application Support/Patcher"
    caches = Path.home() / "Library/Caches/Patcher"
    before = (_snapshot(support), _snapshot(caches))

    result = await CliRunner().invoke(cli, ["-x", "--disable-cache", "reset", "full"])

    after = (_snapshot(support), _snapshot(caches))
    assert before == after, "A CLI test modified the real Patcher directories!"
    assert result.exit_code == 0
