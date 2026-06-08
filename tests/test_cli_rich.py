"""
Unit coverage for the Rich-backed CLI helpers.

Covers two surfaces from the Rich integration: the shared console singletons
and palette constants in ``patcher.cli._console``, and the debug-aware
``status()`` spinner helper that replaced the old ``Animation`` class.

The ``status()`` behaviour is verified by patching ``console.status`` so we
can assert the lifecycle without spawning a real spinner against a terminal.
"""

from unittest.mock import MagicMock, patch

from src.patcher.cli import _console


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
