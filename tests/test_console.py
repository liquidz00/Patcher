"""
Unit coverage for the Rich-backed CLI output layer (``patcher.cli._console``):
console singletons + themed palette, the status spinner, the progress-bar
factory, the table / diff / drift renderers, the error panel, and the
click-backed terminal logging.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text
from src.patcher.cli import _console
from src.patcher.clients.patcher_api import DriftEntry, DriftResponse, SourceVersion
from src.patcher.core.analyze import DiffResult, TitleChange
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.logger import PatcherLog
from src.patcher.core.models.patch import PatchTitle


def _render(renderable) -> str:
    """Render any Rich renderable to plain text for content assertions."""
    cap = Console(width=200, color_system=None)
    with cap.capture() as capture:
        cap.print(renderable)
    return capture.get()


def _pt(title: str = "Firefox", pct: float = 80.0) -> PatchTitle:
    return PatchTitle(
        title=title,
        title_id="1",
        released="2026-01-01",
        hosts_patched=8,
        missing_patch=2,
        latest_version="120.0",
        completion_percent=pct,
        total_hosts=10,
    )


def _change(title: str = "Chrome") -> TitleChange:
    return TitleChange(
        title=title,
        title_id="2",
        from_completion_percent=50.0,
        to_completion_percent=75.0,
        completion_delta=25.0,
        from_hosts_patched=5,
        to_hosts_patched=8,
        from_total_hosts=10,
        to_total_hosts=10,
        from_latest_version="1",
        to_latest_version="2",
        version_changed=True,
    )


def _drift_entry(slug: str = "firefox") -> DriftEntry:
    return DriftEntry(
        slug=slug,
        name="Firefox",
        versions=[
            SourceVersion(source="installomator", version="1.0", parsed_ok=True),
            SourceVersion(source="homebrew_cask", version="2.0", parsed_ok=False),
        ],
        leader="homebrew_cask",
        laggard="installomator",
    )


class TestConsoleModule:
    def test_console_singletons_are_distinct(self):
        assert _console.console is not _console.err_console

    def test_err_console_writes_to_stderr(self):
        assert _console.err_console.stderr is True
        assert _console.console.stderr is False

    def test_palette_constants_are_semantic_names(self):
        assert _console.INFO_STYLE == "info"
        assert _console.WARNING_STYLE == "warning"
        assert _console.ERROR_STYLE == "error"
        assert _console.SUCCESS_STYLE == "success"
        assert _console.DIM_STYLE == "dim"

    def test_theme_resolves_semantic_names_to_colors(self):
        # The console's theme owns the actual colors the names map to.
        styles = _console.console.get_style("warning"), _console.console.get_style("success")
        assert styles[0].color.name == "yellow"
        assert styles[1].color.name == "green"

    def test_spinner_name_constant(self):
        assert _console.SPINNER_NAME == "dots"


class TestNoOpStatus:
    def test_methods_are_safe_noops(self):
        noop = _console._NoOpStatus()
        # None of these should raise or return anything meaningful.
        assert noop.update("anything", extra=True) is None
        assert noop.start() is None
        assert noop.stop() is None


class TestStatusHelper:
    def test_disabled_yields_noop_stand_in(self):
        with _console.status("Working...", enabled=False) as spinner:
            assert isinstance(spinner, _console._NoOpStatus)
            # Calling the surface inside the block must stay a no-op.
            spinner.update("still working")

    def test_disabled_never_touches_console_status(self):
        with patch.object(_console.console, "status") as status_factory:
            with _console.status("Working...", enabled=False):
                pass
        status_factory.assert_not_called()

    def test_enabled_uses_console_status_with_spinner(self):
        fake_cm = MagicMock()
        fake_live = MagicMock()
        fake_cm.__enter__.return_value = fake_live

        with patch.object(_console.console, "status", return_value=fake_cm) as status_factory:
            with _console.status("Working...") as spinner:
                assert spinner is fake_live
                spinner.update("New message")

        status_factory.assert_called_once_with("Working...", spinner="dots")
        fake_cm.__enter__.assert_called_once()
        fake_cm.__exit__.assert_called_once()
        fake_live.update.assert_called_once_with("New message")

    def test_enabled_exits_status_on_exception(self):
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = MagicMock()

        with patch.object(_console.console, "status", return_value=fake_cm):
            try:
                with _console.status("Working..."):
                    raise RuntimeError("boom")
            except RuntimeError:
                pass

        fake_cm.__exit__.assert_called_once()


class TestBuildTable:
    def test_with_headers(self):
        table = _console.build_table([["a", "1"], ["b", "2"]], headers=["Name", "Count"])
        assert isinstance(table, Table)
        assert table.row_count == 2
        assert [col.header for col in table.columns] == ["Name", "Count"]

    def test_headerless_summary(self):
        table = _console.build_table([["key", "value"]])
        assert table.show_header is False
        assert len(table.columns) == 2


class TestRenderDiff:
    def test_returns_group_with_all_sections(self):
        result = DiffResult(
            from_label="A",
            to_label="B",
            from_count=1,
            to_count=2,
            added=[_pt("Firefox")],
            removed=[_pt("Slack")],
            changed=[_change("Chrome")],
            unchanged_count=3,
            avg_completion_delta=5.0,
            version_bumps=[_change("Chrome")],
        )
        out = _console.render_diff(result)
        assert isinstance(out, Group)
        text = _render(out)
        for token in ("Firefox", "Slack", "Chrome", "Added", "Changed", "Removed", "Summary"):
            assert token in text

    def test_empty_diff_still_renders_summary(self):
        result = DiffResult(
            from_label="A",
            to_label="B",
            from_count=0,
            to_count=0,
            added=[],
            removed=[],
            changed=[],
            unchanged_count=0,
        )
        assert "Summary" in _render(_console.render_diff(result))

    def test_changed_without_version_bump_omits_bump_marker(self):
        change = _change("Slack")
        change.version_changed = False  # exercises the non-bump branch
        result = DiffResult(
            from_label="A",
            to_label="B",
            from_count=1,
            to_count=1,
            added=[],
            removed=[],
            changed=[change],
            unchanged_count=0,
        )
        assert "(bump)" not in _render(_console.render_diff(result))


class TestRenderDrift:
    def test_entries_render_as_table(self):
        resp = DriftResponse(total_scanned=10, total_with_drift=1, entries=[_drift_entry()])
        out = _console.render_drift(resp)
        assert isinstance(out, Table)
        assert "firefox" in _render(out)

    def test_empty_returns_text(self):
        resp = DriftResponse(total_scanned=10, total_with_drift=0, entries=[])
        out = _console.render_drift(resp)
        assert isinstance(out, Text)
        assert "No drift detected" in _render(out)

    def test_render_drift_entry(self):
        out = _console.render_drift_entry(_drift_entry())
        assert isinstance(out, Group)
        text = _render(out)
        assert "firefox" in text
        assert "Leader: homebrew_cask" in text


class TestFormatErr:
    def test_renders_message_and_recovery_hint(self):
        with _console.err_console.capture() as cap:
            _console.format_err(PatcherError("kaboom", recovery="run --fresh"))
        out = cap.get()
        assert "kaboom" in out
        assert "Error" in out
        assert "run --fresh" in out

    def test_without_hint(self):
        with _console.err_console.capture() as cap:
            _console.format_err(PatcherError("plain failure"))
        assert "plain failure" in cap.get()


class TestProgressBar:
    def test_returns_progress(self):
        from rich.progress import Progress

        bar = _console.progress_bar()
        assert isinstance(bar, Progress)
        assert bar.disable is False

    def test_disable_flag(self):
        assert _console.progress_bar(disable=True).disable is True


class TestTerminalLogging:
    def test_handler_emit_preserves_brackets(self):
        record = logging.LogRecord("Patcher", logging.WARNING, "f", 1, "msg [x]", None, None)
        with _console.console.capture() as cap:
            _console.TerminalHandler().emit(record)
        out = cap.get()
        assert "WARNING" in out
        assert "msg [x]" in out  # markup=False keeps the literal brackets

    def test_install_handler_is_idempotent(self):
        logger = logging.getLogger(PatcherLog.LOGGER_NAME)
        for handler in [h for h in logger.handlers if isinstance(h, _console.TerminalHandler)]:
            logger.removeHandler(handler)
        try:
            _console.install_terminal_handler(True)
            _console.install_terminal_handler(True)
            assert sum(isinstance(h, _console.TerminalHandler) for h in logger.handlers) == 1
        finally:
            for handler in [h for h in logger.handlers if isinstance(h, _console.TerminalHandler)]:
                logger.removeHandler(handler)

    def test_install_handler_noop_when_not_debug(self):
        logger = logging.getLogger(PatcherLog.LOGGER_NAME)
        before = sum(isinstance(h, _console.TerminalHandler) for h in logger.handlers)
        _console.install_terminal_handler(False)
        after = sum(isinstance(h, _console.TerminalHandler) for h in logger.handlers)
        assert after == before

    def test_setup_logging_wires_file_then_terminal(self, mocker):
        mock_file = mocker.patch("src.patcher.cli._console.PatcherLog.setup_logger")
        mock_term = mocker.patch("src.patcher.cli._console.install_terminal_handler")
        _console.setup_logging(True)
        mock_file.assert_called_once()
        mock_term.assert_called_once_with(True)

    def test_install_excepthook_chains_and_surfaces(self):
        original = sys.excepthook
        try:
            # Patch before install so the hook captures the mocked base hook.
            with patch.object(PatcherLog, "custom_excepthook") as base:
                _console.install_terminal_excepthook()
                assert sys.excepthook is not original
                with _console.err_console.capture() as cap:
                    sys.excepthook(ValueError, ValueError("boom"), None)
                base.assert_called_once()
            assert "ValueError" in cap.get()
        finally:
            sys.excepthook = original

    def test_excepthook_skips_message_on_keyboard_interrupt(self):
        original = sys.excepthook
        try:
            with patch.object(PatcherLog, "custom_excepthook"):
                _console.install_terminal_excepthook()
                with _console.err_console.capture() as cap:
                    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
            assert cap.get() == ""  # early return — no extra stderr message
        finally:
            sys.excepthook = original
