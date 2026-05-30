"""
Unit coverage for the Rich-backed CLI helpers.

Covers two new surfaces from the Rich integration: the shared console
singletons and palette constants in ``patcher.cli._console``, and the
``rich.status.Status``-backed ``Animation`` wrapper.

Animation's behaviour is verified by patching ``rich.status.Status`` so we
can assert lifecycle calls (``start`` / ``stop`` / ``update``) without
spawning a real spinner against a terminal.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.patcher.cli import _console
from src.patcher.cli.animation import Animation


class TestConsoleModule:
    def test_console_singletons_are_distinct(self):
        assert _console.console is not _console.err_console

    def test_err_console_writes_to_stderr(self):
        assert _console.err_console.stderr is True
        assert _console.console.stderr is False

    def test_palette_constants_present(self):
        assert _console.INFO_STYLE == "cyan"
        assert _console.WARNING_STYLE == "yellow"
        assert _console.ERROR_STYLE == "red"
        assert _console.SUCCESS_STYLE == "green"
        assert _console.DIM_STYLE == "dim"


class TestAnimation:
    def test_init_defaults(self):
        anim = Animation()
        assert anim.message_template == "Processing"
        assert anim.enable_animation is True
        assert anim._status is None
        assert anim._started is False

    def test_init_with_custom_message(self):
        anim = Animation(message_template="Fetching titles...", enable_animation=False)
        assert anim.message_template == "Fetching titles..."
        assert anim.enable_animation is False

    @pytest.mark.asyncio
    async def test_start_noop_when_disabled(self):
        anim = Animation(enable_animation=False)
        await anim.start()
        assert anim._status is None
        assert anim._started is False

    @pytest.mark.asyncio
    async def test_start_invokes_status(self):
        anim = Animation(message_template="Working...")
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status) as status_factory:
            await anim.start()
        status_factory.assert_called_once_with("Working...", spinner="dots")
        fake_status.start.assert_called_once()
        assert anim._started is True

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self):
        anim = Animation()
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status) as status_factory:
            await anim.start()
            await anim.start()
        assert status_factory.call_count == 1
        assert fake_status.start.call_count == 1

    @pytest.mark.asyncio
    async def test_update_msg_dispatches_to_status(self):
        anim = Animation()
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status):
            await anim.start()
            await anim.update_msg("New message")
        fake_status.update.assert_called_once_with("New message")
        assert anim.message_template == "New message"

    @pytest.mark.asyncio
    async def test_update_msg_before_start_only_updates_template(self):
        anim = Animation()
        await anim.update_msg("Pending")
        assert anim.message_template == "Pending"

    @pytest.mark.asyncio
    async def test_stop_clears_state_and_flags_event(self):
        anim = Animation()
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status):
            await anim.start()
            await anim.stop()
        fake_status.stop.assert_called_once()
        assert anim._status is None
        assert anim._started is False
        assert anim.stop_event.is_set()

    @pytest.mark.asyncio
    async def test_stop_is_safe_without_start(self):
        anim = Animation()
        await anim.stop()
        assert anim.stop_event.is_set()

    @pytest.mark.asyncio
    async def test_error_handling_stops_on_success(self):
        anim = Animation()
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status):
            async with anim.error_handling():
                fake_status.start.assert_called_once()
        fake_status.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_stops_on_exception(self):
        anim = Animation()
        fake_status = MagicMock()
        with patch.object(_console.console, "status", return_value=fake_status):
            with pytest.raises(RuntimeError, match="boom"):
                async with anim.error_handling():
                    raise RuntimeError("boom")
        fake_status.stop.assert_called_once()
