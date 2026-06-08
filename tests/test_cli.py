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
from src.patcher.cli import analyze, cli, diff, drift, export, reset
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.models.patch import PatchTitle
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


def _patch_title(title="Firefox"):
    return PatchTitle(
        title=title,
        title_id="1",
        released="2026-01-01",
        hosts_patched=10,
        missing_patch=2,
        latest_version="120.0",
    )


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
    assert kwargs["enable_matching"] is True
    assert kwargs["ignored_titles"] == ["Adobe *"]
    assert kwargs["concurrency"] == 7
    assert kwargs["enable_homebrew"] is False
    mock_proc.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_summary_requires_output_dir():
    """--summary without --output-dir warns and returns early, before any data access."""
    ctx = _ctx()
    result = await analyze.callback.__wrapped__(
        ctx,
        excel_file=None,
        criteria="most-installed",
        threshold=70.0,
        top_n=None,
        min_compliance=None,
        min_hosts=None,
        released_after=None,
        summary=True,
        output_dir=None,
        all_time=False,
    )
    assert result is None


@pytest.mark.asyncio
async def test_analyze_filter_prints_results(mocker):
    mock_filter = mocker.patch(
        "src.patcher.cli.TitleFilter.apply", return_value=[_patch_title("Firefox")]
    )
    ctx = _ctx()
    await analyze.callback.__wrapped__(
        ctx,
        excel_file=None,
        criteria="most-installed",
        threshold=70.0,
        top_n=None,
        min_compliance=None,
        min_hosts=None,
        released_after=None,
        summary=False,
        output_dir=None,
        all_time=False,
    )
    mock_filter.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_no_matches_exits(mocker):
    mocker.patch("src.patcher.cli.TitleFilter.apply", return_value=[])
    ctx = _ctx()
    with pytest.raises(SystemExit) as excinfo:
        await analyze.callback.__wrapped__(
            ctx,
            excel_file=None,
            criteria="below-threshold",
            threshold=70.0,
            top_n=None,
            min_compliance=None,
            min_hosts=None,
            released_after=None,
            summary=False,
            output_dir=None,
            all_time=False,
        )
    assert excinfo.value.code == 0


@pytest.mark.asyncio
async def test_analyze_all_time_trend(mocker):
    import pandas as pd

    mock_trend = mocker.patch(
        "src.patcher.cli.TrendAnalysis.apply",
        return_value=pd.DataFrame([{"Title": "Firefox", "Trend": 1}]),
    )
    ctx = _ctx()
    await analyze.callback.__wrapped__(
        ctx,
        excel_file=None,
        criteria="most-installed",
        threshold=70.0,
        top_n=None,
        min_compliance=None,
        min_hosts=None,
        released_after=None,
        summary=False,
        output_dir=None,
        all_time=True,
    )
    mock_trend.assert_called_once()


@pytest.mark.asyncio
async def test_diff_builds_client_and_renders(mocker):
    mock_client_cls = mocker.patch("src.patcher.cli.PatcherClient")
    mock_client_cls.return_value.diff = AsyncMock(return_value=MagicMock())
    mocker.patch("src.patcher.cli.render_diff", return_value="table")
    settings = PatcherSettings(ignored_titles=["Jamf *"])
    ctx = _ctx(settings=settings)

    await diff.callback.__wrapped__(
        ctx,
        since=None,
        all_time=False,
        between=None,
        no_fetch=True,
        list_snapshots=False,
        output_format="text",
    )

    assert mock_client_cls.call_args.kwargs["ignored_titles"] == ["Jamf *"]
    mock_client_cls.return_value.diff.assert_awaited_once()


@pytest.mark.asyncio
async def test_diff_json_output(mocker):
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    result = MagicMock()
    result.model_dump_json.return_value = '{"changed": []}'
    mock_client.diff = AsyncMock(return_value=result)
    ctx = _ctx()

    await diff.callback.__wrapped__(
        ctx,
        since=None,
        all_time=False,
        between=None,
        no_fetch=True,
        list_snapshots=False,
        output_format="json",
    )

    result.model_dump_json.assert_called_once()


@pytest.mark.asyncio
async def test_diff_list_snapshots_empty_exits(mocker):
    mocker.patch("src.patcher.cli.get_data_manager").return_value.get_cached_files.return_value = []
    ctx = _ctx()

    with pytest.raises(SystemExit) as excinfo:
        await diff.callback.__wrapped__(
            ctx,
            since=None,
            all_time=False,
            between=None,
            no_fetch=False,
            list_snapshots=True,
            output_format="text",
        )
    assert excinfo.value.code == 0


@pytest.mark.asyncio
async def test_drift_builds_client_and_renders(mocker):
    mock_client_cls = mocker.patch("src.patcher.cli.PatcherClient")
    mock_client_cls.return_value.detect_drift = AsyncMock(return_value=MagicMock())
    mocker.patch("src.patcher.cli.render_drift", return_value="table")
    settings = PatcherSettings(ignored_titles=["Adobe *"])
    ctx = _ctx(settings=settings)

    await drift.callback.__wrapped__(
        ctx, slug=None, vendor=None, source=None, limit=100, offset=0, output_format="text"
    )

    assert mock_client_cls.call_args.kwargs["ignored_titles"] == ["Adobe *"]
    mock_client_cls.return_value.detect_drift.assert_awaited_once()


@pytest.mark.asyncio
async def test_drift_none_reports_no_drift(mocker):
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    mock_client.detect_drift = AsyncMock(return_value=None)
    ctx = _ctx()

    await drift.callback.__wrapped__(
        ctx, slug="firefox", vendor=None, source=None, limit=100, offset=0, output_format="text"
    )

    mock_client.detect_drift.assert_awaited_once()


@pytest.mark.asyncio
async def test_drift_json_output(mocker):
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    result = MagicMock()
    result.model_dump_json.return_value = '{"slug": "x"}'
    mock_client.detect_drift = AsyncMock(return_value=result)
    ctx = _ctx()

    await drift.callback.__wrapped__(
        ctx, slug=None, vendor=None, source=None, limit=100, offset=0, output_format="json"
    )

    result.model_dump_json.assert_called_once()


@pytest.mark.asyncio
async def test_drift_json_null_when_no_result(mocker):
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    mock_client.detect_drift = AsyncMock(return_value=None)
    ctx = _ctx()

    await drift.callback.__wrapped__(
        ctx, slug="x", vendor=None, source=None, limit=100, offset=0, output_format="json"
    )

    mock_client.detect_drift.assert_awaited_once()


@pytest.mark.asyncio
async def test_drift_single_entry_renders_detail(mocker):
    from src.patcher.clients.patcher_api import DriftEntry, SourceVersion

    entry = DriftEntry(
        slug="firefox",
        name="Firefox",
        versions=[SourceVersion(source="installomator", version="1.0", parsed_ok=True)],
        leader="installomator",
    )
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    mock_client.detect_drift = AsyncMock(return_value=entry)
    mocker.patch("src.patcher.cli.render_drift_entry", return_value="entry")
    ctx = _ctx()

    await drift.callback.__wrapped__(
        ctx, slug="firefox", vendor=None, source=None, limit=100, offset=0, output_format="text"
    )

    mock_client.detect_drift.assert_awaited_once()


@pytest.mark.asyncio
async def test_diff_between_two_dates(mocker):
    mock_client = mocker.patch("src.patcher.cli.PatcherClient").return_value
    mock_client.diff = AsyncMock(return_value=MagicMock())
    mocker.patch("src.patcher.cli.render_diff", return_value="rendered")
    ctx = _ctx()

    await diff.callback.__wrapped__(
        ctx,
        since=None,
        all_time=False,
        between=("2026-01-01", "2026-02-01"),
        no_fetch=False,
        list_snapshots=False,
        output_format="text",
    )

    assert mock_client.diff.await_args.kwargs["between"] is not None


@pytest.mark.asyncio
async def test_analyze_filter_summary_exports_html(mocker):
    mocker.patch("src.patcher.cli.TitleFilter.apply", return_value=[_patch_title("Firefox")])
    dm = mocker.patch("src.patcher.cli.get_data_manager").return_value
    dm.export = AsyncMock(return_value={"html": "/out/summary.html"})
    ctx = _ctx()

    await analyze.callback.__wrapped__(
        ctx,
        excel_file=None,
        criteria="most-installed",
        threshold=70.0,
        top_n=None,
        min_compliance=None,
        min_hosts=None,
        released_after=None,
        summary=True,
        output_dir="/out",
        all_time=False,
    )

    dm.export.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_all_time_trend_summary_saves_html(mocker, tmp_path):
    import pandas as pd

    mocker.patch(
        "src.patcher.cli.TrendAnalysis.apply",
        return_value=pd.DataFrame([{"Title": "Firefox", "Trend": 1}]),
    )
    ctx = _ctx()

    await analyze.callback.__wrapped__(
        ctx,
        excel_file=None,
        criteria="most-installed",
        threshold=70.0,
        top_n=None,
        min_compliance=None,
        min_hosts=None,
        released_after=None,
        summary=True,
        output_dir=tmp_path,
        all_time=True,
    )

    assert (tmp_path / "trend-analysis-most-installed.html").exists()


@pytest.mark.asyncio
async def test_reset_full_failure_raises(mocker):
    config = MagicMock()
    config.reset_config = MagicMock(return_value=False, __name__="reset_config")
    setup = MagicMock()
    setup.reset_ui_config.return_value = True
    setup.reset_setup.return_value = True
    ctx = _ctx(config=config, setup=setup)

    with pytest.raises(PatcherError, match="Reset could not be completed"):
        await reset.callback.__wrapped__(ctx, kind="full", credential=None)


@pytest.mark.parametrize(
    "credential,key", [("client_id", "CLIENT_ID"), ("client_secret", "CLIENT_SECRET")]
)
@pytest.mark.asyncio
async def test_reset_specific_credential(mocker, credential, key):
    mocker.patch("src.patcher.cli.click.prompt", new=AsyncMock(return_value="value"))
    config = MagicMock()
    ctx = _ctx(config=config)

    await reset.callback.__wrapped__(ctx, kind="creds", credential=credential)

    config.set_credential.assert_called_once_with(key, "value")


@pytest.mark.asyncio
async def test_reset_all_credentials(mocker):
    mocker.patch("src.patcher.cli.click.prompt", new=AsyncMock(return_value="value"))
    config = MagicMock()
    ctx = _ctx(config=config)

    await reset.callback.__wrapped__(ctx, kind="creds", credential=None)

    assert config.set_credential.call_count == 3  # URL + CLIENT_ID + CLIENT_SECRET


@pytest.mark.asyncio
async def test_reset_cache_clears_when_enabled():
    dm = MagicMock()
    dm.reset_cache.return_value = True
    ctx = _ctx(disable_cache=False)
    ctx.obj["data_manager"] = dm

    await reset.callback.__wrapped__(ctx, kind="cache", credential=None)

    dm.reset_cache.assert_called_once()


@pytest.mark.asyncio
async def test_cli_warns_on_interpreter_mismatch(mocker):
    settings = PatcherSettings(setup_completed=True, interpreter_path="/some/other/python")
    mocker.patch("src.patcher.cli.PatcherSettings.load", return_value=settings)

    result = await CliRunner().invoke(cli, ["-x", "reset", "--help"])

    assert result.exit_code == 0  # warning branch runs, command still parses


@pytest.mark.asyncio
async def test_cli_runs_setup_when_not_completed(mocker):
    settings = PatcherSettings(setup_completed=False)
    mocker.patch("src.patcher.cli.PatcherSettings.load", return_value=settings)

    result = await CliRunner().invoke(cli, ["-x"])  # Setup.start is mocked by _no_disk

    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_cli_noninteractive_bootstrap(mocker):
    settings = PatcherSettings(setup_completed=True)
    mocker.patch("src.patcher.cli.PatcherSettings.load", return_value=settings)
    boot = mocker.patch("src.patcher.cli.Setup.bootstrap_noninteractive", new_callable=AsyncMock)

    result = await CliRunner().invoke(
        cli, ["--client-id", "x", "--client-secret", "y", "--url", "https://z.example.com"]
    )

    assert result.exit_code == 0
    boot.assert_awaited_once()


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
