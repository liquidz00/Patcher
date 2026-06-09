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
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from ..clients.patcher_api import DriftEntry, DriftResponse
from ..core.analyze import DiffResult
from ..core.exceptions import PatcherError
from ..core.logger import PatcherLog
from ..core.models.patch import PatchTitle

# Semantic palette. Callsites reference the names (``style="warning"``); the
# theme owns the colors, so the whole palette changes in one place.
_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "red",
        "success": "green",
        "banner": "bold cyan",  # welcome/setup heading — a theme alias can't combine with `bold` inline
        "markdown.code": "bold cyan",
    }
)
console = Console(theme=_THEME)
err_console = Console(stderr=True, theme=_THEME)

INFO_STYLE = "info"
WARNING_STYLE = "warning"
ERROR_STYLE = "error"
SUCCESS_STYLE = "success"
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


def progress_bar(*, disable: bool = False) -> Progress:
    """
    A consistently-styled Rich progress display (spinner + description + bar).

    Determinate when a task's ``total`` is set (the bar fills); pulsing while
    ``total`` is ``None``. Pass ``disable=debug`` so ``--debug`` runs skip the
    live display and let log lines flow uninterrupted.

    :param disable: When True the display renders nothing (debug runs).
    :type disable: bool
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
        disable=disable,
    )


def build_table(
    rows: list[list],
    headers: list[str] | None = None,
    *,
    title: str | None = None,
    caption: str | None = None,
    justify: list[str] | None = None,
    no_wrap: list[bool] | None = None,
    footer: list | None = None,
    lines: bool = False,
) -> Table:
    """
    Build a Rich :class:`~rich.table.Table` from row data.

    Cells that are already Rich renderables (e.g. a styled :class:`~rich.text.Text`)
    pass through untouched, so callers can color individual cells; everything else
    is stringified.

    :param rows: Row data; each cell is a string, a value, or a Rich renderable.
    :type rows: list[list]
    :param headers: Optional column headers. When omitted the table renders
        headerless (used for key/value summaries).
    :type headers: list[str] | None
    :param title: Optional bold title rendered above the table.
    :type title: str | None
    :param caption: Optional dim line rendered below the table (run provenance).
    :type caption: str | None
    :param justify: Optional per-column justification (e.g. ``"right"`` for numbers).
    :type justify: list[str] | None
    :param no_wrap: Optional per-column wrap suppression (truncate with an ellipsis).
    :type no_wrap: list[bool] | None
    :param footer: Optional per-column footer cells; presence enables the footer row.
    :type footer: list | None
    :param lines: Draw a horizontal divider between every row (for scannable data tables).
    :type lines: bool
    """
    table = Table(
        title=title,
        caption=caption,
        title_style="bold",
        header_style="bold",
        title_justify="left",
        caption_justify="left",
        show_footer=footer is not None,
        show_lines=lines,
    )
    if headers:
        for index, head in enumerate(headers):
            table.add_column(
                str(head),
                justify=justify[index] if justify else "left",
                no_wrap=no_wrap[index] if no_wrap else False,
                overflow="ellipsis",
                footer=footer[index] if footer else "",
            )
    else:
        table.show_header = False
        for _ in range(max((len(row) for row in rows), default=1)):
            table.add_column()
    for row in rows:
        table.add_row(*(cell if isinstance(cell, Text) else str(cell) for cell in row))
    return table


def completion_text(percent: float, threshold: float) -> Text:
    """
    Render a completion percentage as a health-colored cell.

    Red below ``threshold``, yellow up to 90%, green at 90% or above, so a fleet's
    laggards jump out of the table at a glance.

    :param percent: Completion percentage (0-100).
    :type percent: float
    :param threshold: The cutoff below which a title reads as out of compliance.
    :type threshold: float
    """
    if percent < threshold:
        style = ERROR_STYLE
    elif percent < 90:
        style = WARNING_STYLE
    else:
        style = SUCCESS_STYLE
    return Text(f"{percent:.1f}%", style=style)


def build_fleet_summary(titles: list[PatchTitle], threshold: float) -> Panel:
    """
    Summarize fleet-wide patch compliance as a single at-a-glance panel.

    :param titles: The full set of cached patch titles (not the filtered view).
    :type titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
    :param threshold: Completion cutoff used to count titles out of compliance.
    :type threshold: float
    """
    total = len(titles)
    avg = sum(t.completion_percent for t in titles) / total if total else 0.0
    below = sum(1 for t in titles if t.completion_percent < threshold)
    total_hosts = sum(t.total_hosts for t in titles)
    total_patched = sum(t.hosts_patched for t in titles)

    body = Text.assemble(
        ("Titles ", DIM_STYLE),
        (f"{total}", "bold"),
        ("    Avg completion ", DIM_STYLE),
        completion_text(avg, threshold),
        (f"    Below {threshold:g}% ", DIM_STYLE),
        (f"{below}", ERROR_STYLE if below else SUCCESS_STYLE),
        ("    Hosts patched ", DIM_STYLE),
        (f"{total_patched}/{total_hosts}", "bold"),
    )
    return Panel(body, title="Fleet Compliance", border_style=INFO_STYLE, expand=False)


def render_diff(result: DiffResult) -> Group:
    """Render a :class:`DiffResult` as Rich tables grouped by section."""
    parts: list = [Text(f"Diff: {result.from_label} → {result.to_label}", style="bold")]

    if result.added:
        parts.append(
            build_table(
                [
                    [t.title, t.released, t.hosts_patched, f"{t.completion_percent:.1f}%"]
                    for t in result.added
                ],
                headers=["Title", "Released", "Hosts", "Complete"],
                title=f"Added ({len(result.added)})",
            )
        )

    if result.changed:
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
        parts.append(
            build_table(
                rows,
                headers=["Title", "Complete %", "Hosts", "Version"],
                title=f"Changed ({len(result.changed)})",
            )
        )

    if result.removed:
        parts.append(
            build_table(
                [[t.title, t.released, t.hosts_patched] for t in result.removed],
                headers=["Title", "Last released", "Hosts"],
                title=f"Removed ({len(result.removed)})",
            )
        )

    summary_rows = [
        ["Titles", f"{result.from_count} → {result.to_count}"],
        ["Unchanged", str(result.unchanged_count)],
        ["Version bumps", str(len(result.version_bumps))],
    ]
    if result.avg_completion_delta is not None:
        summary_rows.append(["Avg completion Δ", f"{result.avg_completion_delta:+.2f}pp"])
    parts.append(build_table(summary_rows, title="Summary"))

    return Group(*parts)


def render_drift(result: DriftResponse) -> Table | Text:
    """Render a :class:`DriftResponse` as a Rich table summary."""
    if not result.entries:
        return Text(f"No drift detected. Scanned {result.total_scanned} eligible apps.")

    rows = [
        [
            entry.slug,
            entry.name,
            ", ".join(f"{v.source}={v.version}" for v in entry.versions),
            entry.leader or "—",
        ]
        for entry in result.entries
    ]
    return build_table(
        rows,
        headers=["Slug", "Name", "Versions", "Leader"],
        title=(
            f"Drift across {result.total_with_drift} apps "
            f"({result.total_scanned} scanned, showing {len(result.entries)})"
        ),
    )


def render_drift_entry(entry: DriftEntry) -> Group:
    """Render a single :class:`DriftEntry` with per-source version detail."""
    parts: list = [
        build_table(
            [[v.source, v.version, "yes" if v.parsed_ok else "no"] for v in entry.versions],
            headers=["Source", "Version", "Parseable"],
            title=f"Drift: {entry.name} ({entry.slug})",
        )
    ]
    if entry.leader is not None:
        parts.append(Text(f"Leader: {entry.leader}    Laggard: {entry.laggard}", style="dim"))
    return Group(*parts)


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

        # PatcherErrors carry recovery context — render them in the styled panel.
        if isinstance(exc_value, PatcherError):
            format_err(exc_value)
            return

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
