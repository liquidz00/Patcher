"""
Click-backed terminal output for the Patcher logger.

This module is the CLI's adapter onto :class:`patcher.core.logger.PatcherLog`.
Installing a :class:`TerminalHandler` adds colored level-prefixed output on top
of the always-present rotating file handler; library users who never import
``patcher.cli`` get the file-only behavior with no ``asyncclick`` dependency.

Two install points:

- :func:`install_terminal_handler`: attach the colored console handler.
  Call from the CLI entry point when ``--debug`` is set.
- :func:`install_terminal_excepthook`: chain a terminal-styled message onto
  :meth:`patcher.core.logger.PatcherLog.custom_excepthook` so unhandled
  exceptions surface a one-line stderr message in addition to the file log.
"""

import logging
import sys
from types import TracebackType
from typing import Type

import asyncclick as click

from ..core.logger import PatcherLog


class TerminalHandler(logging.Handler):
    """
    Logging handler that emits records as click-styled lines on stdout.

    Maps each log level to a color so a debug run produces the same visual
    output the legacy in-class ``click.echo`` calls did (magenta DEBUG, blue
    INFO, bold-yellow WARNING, bold-red ERROR. The leading ``\\r`` preserves
    the existing behavior of overwriting the current terminal line (used to
    coexist with the :class:`~patcher.cli.animation.Animation` spinner).
    """

    LEVEL_STYLES: dict[int, dict] = {
        logging.DEBUG: {"fg": "magenta"},
        logging.INFO: {"fg": "blue"},
        logging.WARNING: {"fg": "yellow", "bold": True},
        logging.ERROR: {"fg": "red", "bold": True},
    }

    def emit(self, record: logging.LogRecord) -> None:
        style = self.LEVEL_STYLES.get(record.levelno, {})
        line = f"\r{record.levelname}: {record.getMessage().strip()}"
        click.echo(click.style(line, **style))


def install_terminal_handler(debug: bool) -> None:
    """
    Attach a :class:`TerminalHandler` to the Patcher logger when in debug mode.

    Idempotent. Calling twice will not add duplicate handlers. No-op when
    ``debug`` is False, so the standard CLI run (and any library import path)
    sees no terminal output beyond what callers explicitly emit.

    :param debug: Whether the CLI was invoked with ``--debug``.
    :type debug: bool
    """
    if not debug:
        return

    logger = logging.getLogger(PatcherLog.LOGGER_NAME)
    if any(isinstance(h, TerminalHandler) for h in logger.handlers):
        return

    handler = TerminalHandler()
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def install_terminal_excepthook() -> None:
    """
    Chain a terminal-styled excepthook onto :meth:`PatcherLog.custom_excepthook`.

    The core hook logs unhandled exceptions to file. This wrapper additionally
    emits a one-line red error message and a hint about the log file to
    stderr, matching the legacy in-module behavior. Library callers who never
    import ``patcher.cli`` are unaffected; their ``sys.excepthook`` is not
    touched.
    """
    base_hook = PatcherLog.custom_excepthook

    def hook(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        base_hook(exc_type, exc_value, exc_traceback)
        if exc_type.__name__ == "KeyboardInterrupt":
            return  # base_hook already exits 130

        click.echo(
            click.style(f"❌ {exc_type.__name__}: {exc_value}", fg="red", bold=True),
            err=True,
        )
        click.echo(
            f"💡 For more details, please check the log file at: '{PatcherLog.LOG_FILE}'",
            err=True,
        )

    sys.excepthook = hook
