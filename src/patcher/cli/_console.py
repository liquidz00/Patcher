"""
Terminal output layer for the Patcher CLI.

Owns everything the CLI puts on the terminal: the shared Rich console
singletons and palette, the debug-aware status spinner, the table / diff /
drift renderers, the error panel, and the logging that routes through the
console (the terminal handler and excepthook). Library callers who never
import ``patcher.cli`` get file-only logging and pay for none of this.

.. versionchanged:: 3.3.0
    Absorbed the former ``terminal_logger`` module and the CLI's rendering
    helpers so all terminal-output concerns live in one place.
"""

import logging
import sys
from contextlib import contextmanager
from types import TracebackType
from typing import Type

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..clients.patcher_api import DriftEntry, DriftResponse
from ..core.analyze import DiffResult
from ..core.exceptions import PatcherError
from ..core.logger import PatcherLog

console = Console()
err_console = Console(stderr=True)

INFO_STYLE = "cyan"
WARNING_STYLE = "yellow"
ERROR_STYLE = "red"
SUCCESS_STYLE = "green"
DIM_STYLE = "dim"
SPINNER_NAME = "dots"


class _NoOpStatus:
    """
    Stand-in for Rich's Status when animation is disabled (e.g. --debug runs).

    Mirrors the surface CLI code calls on a live status (update / start / stop)
    so callers never branch on whether animation is enabled.
    """

    def update(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class TerminalHandler(logging.Handler):
    """
    Logging handler that emits records as Rich-styled lines on stdout.

    Maps each log level to a color so a debug run produces the same visual
    output the legacy in-class ``click.echo`` calls did (magenta DEBUG, blue
    INFO, bold-yellow WARNING, bold-red ERROR). The leading ``\\r`` preserves
    the existing behavior of overwriting the current terminal line. Output
    routes through the shared :data:`console`.
    """

    LEVEL_STYLES: dict[int, str] = {
        logging.DEBUG: "magenta",
        logging.INFO: "blue",
        logging.WARNING: "bold yellow",
        logging.ERROR: "bold red",
    }

    def emit(self, record: logging.LogRecord) -> None:
        style = self.LEVEL_STYLES.get(record.levelno)
        line = f"\r{record.levelname}: {record.getMessage().strip()}"
        # markup=False: log messages can carry literal brackets we must not parse as Rich markup.
        console.print(line, style=style, markup=False)


@contextmanager
def status(message: str = "Processing", *, enabled: bool = True, spinner: str = SPINNER_NAME):
    """
    Debug-aware Rich status spinner.

    Yields a live :class:`rich.status.Status` when ``enabled`` is True, or a
    no-op stand-in with the same ``update`` / ``start`` / ``stop`` surface when
    disabled. Use ``enabled=not debug`` so ``--debug`` runs skip the spinner and
    let log lines flow uninterrupted.

    :param message: Initial message rendered next to the spinner.
    :type message: str
    :param enabled: When False, yields a :class:`_NoOpStatus` instead of a live spinner.
    :type enabled: bool
    :param spinner: Name of the Rich spinner to render.
    :type spinner: str
    """
    if not enabled:
        yield _NoOpStatus()
        return
    with console.status(message, spinner=spinner) as live:
        yield live


def format_table(data: list[list], headers: list[str] | None = None) -> str:
    """Render ``data`` as a fixed-width pipe-separated table for terminal output."""
    if headers:
        data = [headers] + data

    column_widths = [max(len(str(item)) for item in column) for column in zip(*data)]
    format_string = " | ".join(f"{{:<{width}}}" for width in column_widths)
    rows = [format_string.format(*row) for row in data]

    if headers:
        separator = "-+-".join("-" * width for width in column_widths)
        rows.insert(1, separator)

    return "\n".join(rows)


def render_diff(result: DiffResult) -> str:
    """Render a :class:`DiffResult` as a human-readable multi-section table."""
    sections: list[str] = [
        f"Diff: {result.from_label} → {result.to_label}",
        "─" * 60,
        "",
    ]

    if result.added:
        sections.append(f"ADDED ({len(result.added)})")
        rows = [
            [t.title, t.released, t.hosts_patched, f"{t.completion_percent:.1f}%"]
            for t in result.added
        ]
        sections.append(format_table(rows, headers=["Title", "Released", "Hosts", "Complete"]))
        sections.append("")

    if result.changed:
        sections.append(f"CHANGED ({len(result.changed)})")
        rows = []
        for c in result.changed:
            delta_str = f"{c.from_completion_percent:.1f}% → {c.to_completion_percent:.1f}%"
            hosts_str = f"{c.from_hosts_patched} → {c.to_hosts_patched}"
            if c.version_changed:
                version_str = (
                    f"{c.from_latest_version or '?'} → {c.to_latest_version or '?'} (bump)"
                )
            else:
                version_str = c.to_latest_version or "—"
            rows.append([c.title, delta_str, hosts_str, version_str])
        sections.append(format_table(rows, headers=["Title", "Complete %", "Hosts", "Version"]))
        sections.append("")

    if result.removed:
        sections.append(f"REMOVED ({len(result.removed)})")
        rows = [[t.title, t.released, t.hosts_patched] for t in result.removed]
        sections.append(format_table(rows, headers=["Title", "Last released", "Hosts"]))
        sections.append("")

    summary_rows = [
        ["Titles", f"{result.from_count} → {result.to_count}"],
        ["Unchanged", str(result.unchanged_count)],
        ["Version bumps", str(len(result.version_bumps))],
    ]
    if result.avg_completion_delta is not None:
        summary_rows.append(["Avg completion Δ", f"{result.avg_completion_delta:+.2f}pp"])
    sections.append("SUMMARY")
    sections.append(format_table(summary_rows))

    return "\n".join(sections)


def render_drift(result: DriftResponse) -> str:
    """Render a :class:`DriftResponse` as a multi-row table summary."""
    if not result.entries:
        return f"No drift detected. Scanned {result.total_scanned} eligible apps."

    lines = [
        f"Drift across {result.total_with_drift} apps ({result.total_scanned} scanned). Showing {len(result.entries)}.",
        "─" * 60,
        "",
    ]
    rows = []
    for entry in result.entries:
        version_str = ", ".join(f"{v.source}={v.version}" for v in entry.versions)
        leader_str = entry.leader or "—"
        rows.append([entry.slug, entry.name, version_str, leader_str])
    lines.append(format_table(rows, headers=["Slug", "Name", "Versions", "Leader"]))
    return "\n".join(lines)


def render_drift_entry(entry: DriftEntry) -> str:
    """Render a single :class:`DriftEntry` with per-source version detail."""
    lines = [
        f"Drift: {entry.name} ({entry.slug})",
        "─" * 60,
        "",
    ]
    rows = [[v.source, v.version, "yes" if v.parsed_ok else "no"] for v in entry.versions]
    lines.append(format_table(rows, headers=["Source", "Version", "Parseable"]))
    if entry.leader is not None:
        lines.append("")
        lines.append(f"Leader: {entry.leader}    Laggard: {entry.laggard}")
    return "\n".join(lines)


def format_err(exc: PatcherError) -> None:
    """
    Render a :class:`~patcher.core.exceptions.PatcherError` in a red-bordered Rich panel on stderr.

    The panel body carries the exception message in red. If the exception
    exposes a ``recovery`` or ``remediation`` attribute (PatcherError lifts
    keyword context onto the instance), it is rendered as a dim paragraph
    below the main message. A dim rule separates the log-file pointer from
    the error content.

    :param exc: The PatcherError exception to format.
    :type exc: :class:`~patcher.core.exceptions.PatcherError`
    """
    message = Text(str(exc), style=ERROR_STYLE)

    hint = getattr(exc, "recovery", None) or getattr(exc, "remediation", None)
    if hint:
        message.append("\n\n")
        message.append(Text.from_markup(f"[dim]Recovery:[/] {hint}"))

    log_hint = Text.from_markup(
        f"[dim]For more details, see the log file at:[/]\n[dim]{PatcherLog.LOG_FILE}[/]"
    )

    err_console.print(
        Panel(
            Group(message, Rule(style=DIM_STYLE), log_hint),
            title="[bold red]Error[/]",
            border_style=ERROR_STYLE,
            expand=False,
        )
    )


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
    Chain a terminal-styled excepthook onto :meth:`~patcher.core.logger.PatcherLog.custom_excepthook`.

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

        err_console.print(f"❌ {exc_type.__name__}: {exc_value}", style="bold red", markup=False)
        err_console.print(
            f"💡 For more details, please check the log file at: '{PatcherLog.LOG_FILE}'",
            markup=False,
        )

    sys.excepthook = hook


def setup_logging(debug: bool) -> None:
    """
    Configure Patcher logging for the CLI process.

    Installs the always-on rotating file handler, then attaches the
    click-backed terminal handler when ``debug`` is true so debug runs surface
    colored, level-prefixed output to stdout.

    :param debug: Whether to enable debug-level console output.
    :type debug: bool
    """
    PatcherLog.setup_logger()
    install_terminal_handler(debug)
