import asyncio
import inspect
import re
import sys
import warnings
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import asyncclick as click
import rich.traceback
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..__about__ import __version__
from ..clients.patcher_api import DriftEntry, DriftResponse
from ..core.analyze import DiffResult, TitleFilter, TrendAnalysis
from ..core.config_manager import ConfigManager
from ..core.data_manager import DataManager
from ..core.exceptions import APIResponseError, InstallomatorWarning, PatcherError, SetupError
from ..core.logger import LogMe, PatcherLog
from ..core.models.ui import UIDefaults
from ..core.patcher_client import PatcherClient
from ..core.plist_manager import PropertylistManager
from ._console import (
    DIM_STYLE,
    ERROR_STYLE,
    SUCCESS_STYLE,
    WARNING_STYLE,
    console,
    err_console,
    status,
)
from .report import process_reports
from .setup import Setup
from .terminal_logger import install_terminal_excepthook, install_terminal_handler
from .ui_manager import UIConfigManager

# show_locals=False keeps tracebacks safe to paste publicly (no leaked tokens).
# Suppressing asyncclick collapses the framework's own frames so only Patcher
# code shows up. The project doesn't depend on stdlib click; asyncclick is the
# async fork imported as `click` throughout the codebase.
rich.traceback.install(show_locals=False, suppress=[click])

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}

# Context settings to enable both ``-h`` and ``--help`` for help output
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
_SINCE_PATTERN = re.compile(r"^(\d+)([dhw])$")  # short window: 30d / 24h / 1w


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


def parse_since(value: str) -> timedelta:
    """Parse a short window like ``'30d'``, ``'24h'``, ``'1w'`` into a timedelta."""
    match = _SINCE_PATTERN.match(value.strip().lower())
    if not match:
        raise PatcherError(
            "Invalid --since format. Use a number followed by 'd', 'h', or 'w' (e.g. '30d', '24h', '1w').",
            received=value,
        )
    quantity, unit = int(match.group(1)), match.group(2)
    units = {"d": "days", "h": "hours", "w": "weeks"}
    return timedelta(**{units[unit]: quantity})


def parse_iso_date(value: str) -> date:
    """Parse ``'2026-05-17'``-style ISO date strings."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise PatcherError(
            "Invalid date format. Use ISO YYYY-MM-DD (e.g. '2026-05-17').",
            received=value,
            error_msg=str(exc),
        )


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


def setup_logging(debug: bool) -> None:
    """
    Configures Patcher logging for the CLI process.

    Installs the always-on rotating file handler, then attaches the
    click-backed terminal handler when ``debug`` is true so debug runs
    surface colored, level-prefixed output to stdout.

    :param debug: Whether to enable debug-level console output.
    :type debug: bool
    """
    PatcherLog.setup_logger()
    install_terminal_handler(debug)


def format_err(exc: PatcherError) -> None:
    """
    Render a :class:`PatcherError` in a red-bordered Rich panel on stderr.

    The panel body carries the exception message in red. If the exception
    exposes a ``recovery`` or ``remediation`` attribute (PatcherError lifts
    keyword context onto the instance), it is rendered as a dim paragraph
    below the main message. A dim rule separates the log-file pointer from
    the error content.

    :param exc: The PatcherError exception to format.
    :type exc: PatcherError
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


def get_data_manager(ctx: click.Context) -> DataManager:
    """
    Lazily initializes and returns the shared ``DataManager`` instance.

    This ensures consistent handling of ``DataManager`` objects. Inconsistent handling of said objects could lead to inaccurate patch reports or false errors getting raised.

    :param ctx: Click context object.
    :type ctx: `click.Context <https://click.palletsprojects.com/en/stable/api/#click.Context>`_
    :return: The initialized ``DataManager`` instance.
    :rtype: :class:`~patcher.core.data_manager.DataManager`
    """
    if "data_manager" not in ctx.obj or ctx.obj.get("data_manager") is None:
        ctx.obj["data_manager"] = DataManager(disable_cache=ctx.obj.get("disable_cache", False))
    return ctx.obj["data_manager"]


def initialize_cache(cache_dir: Path) -> None:
    """
    Ensures the cache directory exists while avoiding creating system-managed directories.

    :param cache_dir: The full path to the cache directory (e.g., ~/Library/Caches/Patcher).
    :type cache_dir: ~pathlib.Path
    """
    log = LogMe(inspect.currentframe().f_code.co_name)

    parent_dir = cache_dir.parent
    if not parent_dir.exists():
        log.warning(f"Parent directory {parent_dir} does not exist. Skipping cache setup.")
        return

    try:
        cache_dir.mkdir(parents=False, exist_ok=True)
        log.debug(f"Cache directory initialized at {cache_dir}")
    except OSError as err:
        log.warning(f"Failed to initialize cache directory. Details: {err}")
        return


def warning_format(message, category, filename, lineno, file=None, line=None):
    return f"{category.__name__}: {message}\n"


def _install_cli_process_hooks() -> None:
    """
    Apply process-wide side effects scoped to a CLI invocation.

    Kept inside the ``cli()`` callback rather than at module import time so
    importing ``patcher.cli.setup`` (or anything else under ``patcher.cli``)
    from library code does not mutate ``sys.excepthook`` or the global
    warnings filter as a side effect.
    """
    install_terminal_excepthook()
    warnings.simplefilter("always", InstallomatorWarning)
    warnings.formatwarning = warning_format


# Entry
@click.group(
    context_settings=CONTEXT_SETTINGS,
    options_metavar="<options>",
    invoke_without_command=True,
    no_args_is_help=True,
)
@click.version_option(version=__version__)
@click.option("--debug", "-x", is_flag=True, help="Enable debug logging (verbose mode).")
@click.option(
    "--disable-cache", is_flag=True, help="Disable automatic caching of patch report data."
)
@click.option(
    "--fresh", is_flag=True, help="Start setup from scratch, ingoring previously saved progress."
)
@click.option(
    "--client-id",
    envvar="PATCHER_CLIENT_ID",
    metavar="<client_id>",
    help=(
        "Jamf Pro API client ID. When passed alongside --client-secret and --url "
        "(or via PATCHER_CLIENT_ID, PATCHER_CLIENT_SECRET, PATCHER_URL env vars), "
        "Patcher runs in non-interactive mode without keychain access (intended "
        "for CI/CD environments."
    ),
)
@click.option(
    "--client-secret",
    envvar="PATCHER_CLIENT_SECRET",
    metavar="<client_secret>",
    help="Jamf Pro API client secret. See --client-id for non-interactive mode notes.",
)
@click.option(
    "--url",
    envvar="PATCHER_URL",
    metavar="<jamf_url>",
    help="Jamf Pro instance URL. See --client-id for non-interactive mode notes.",
)
@click.pass_context
async def cli(
    ctx: click.Context,
    debug: bool,
    disable_cache: bool,
    fresh: bool,
    client_id: str | None,
    client_secret: str | None,
    url: str | None,
) -> None:
    """
    Main CLI entry point for Patcher.

    Visit our project documentation for full details: https://docs.patcherctl.dev.

    \b
    Exit Codes:
        0   Success
        1   General error (e.g., PatcherError or user-facing issue)
        2   Unhandled exception
        3   Setup error
        4   API error (e.g., unauthorized, invalid response)
        130 KeyboardInterrupt (Ctrl+C)
    \f

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: `click.Context <https://click.palletsprojects.com/en/stable/api/#click.Context>`_
    :param debug: Enables debug (verbose) logging if ``True``. Defaults to ``False``.
    :type debug: bool
    :param disable_cache: Disables automatic caching of patch report data if ``True``. Defaults to ``False``.
    :type disable_cache: bool
    :param fresh: If ``True``, forces the setup assistant to start from scratch. Defaults to ``False``.
    :type fresh: bool
    :param client_id: Jamf Pro API client ID for non-interactive mode.
    :type client_id: str | None
    :param client_secret: Jamf Pro API client secret for non-interactive mode.
    :type client_secret: str | None
    :param url: Jamf Pro instance URL for non-interactive mode.
    :type url: str | None
    """
    setup_logging(debug)
    _install_cli_process_hooks()

    if not disable_cache:
        cache_dir = Path.home() / "Library/Caches/Patcher"
        initialize_cache(cache_dir)

    # Non-interactive mode is engaged when all three credentials are present
    # (via flags or PATCHER_* env vars). In that mode we bypass the keychain
    # and skip every interactive prompt.
    noninteractive = bool(client_id and client_secret and url)

    config_manager = ConfigManager(in_memory_credentials={}) if noninteractive else ConfigManager()

    # Instantiate classes, store in context
    ctx.obj = {
        "debug": debug,
        "disable_cache": disable_cache,
        "noninteractive": noninteractive,
        "log": LogMe(__name__),
        "plist_manager": PropertylistManager(),
        "config": config_manager,
        "ui_config": UIConfigManager(),
    }

    setup = Setup(ctx.obj.get("config"), ctx.obj.get("ui_config"), ctx.obj.get("plist_manager"))
    ctx.obj["setup"] = setup

    # Check Setup completion
    with status("Processing", enabled=not debug) as spinner:
        if not noninteractive and ctx.obj.get("plist_manager").needs_migration():
            ctx.obj.get("plist_manager").migrate_plist()

        # Warn on Python interpreter mismatch. Keychain writes (e.g. token refresh)
        # may fail with errSecInvalidOwnerEdit, but reads work fine so don't block:
        # the run may succeed entirely if no write is needed. See #68.
        if not noninteractive and setup.completed and not fresh:
            recorded_interpreter = ctx.obj.get("plist_manager").get("interpreter_path")
            if recorded_interpreter and recorded_interpreter != sys.executable:
                err_console.print(
                    f"Warning: Patcher was set up under a different Python interpreter:\n"
                    f"  recorded: {recorded_interpreter}\n"
                    f"  current:  {sys.executable}\n\n"
                    f"macOS Keychain ACLs may block this interpreter from updating saved "
                    f"credentials (e.g. on token refresh). Reads work fine; only writes are at risk.\n"
                    f"If you hit a -25244 / errSecInvalidOwnerEdit error mid-run, recover with:\n"
                    f"  security delete-generic-password -s Patcher\n"
                    f"  patcherctl --fresh",
                    style=WARNING_STYLE,
                )

        if noninteractive:
            await setup.bootstrap_noninteractive(
                client_id=client_id, client_secret=client_secret, url=url
            )
            # Fall through; let the requested subcommand run.
        elif not setup.completed or fresh:
            await setup.start(spinner=spinner, fresh=fresh)
            console.print("Setup has completed successfully!", style=SUCCESS_STYLE)
            console.print(
                "Patcher is now ready for use. You can use the --help flag to view available options."
            )
            console.print(
                "For more information, visit the project docs: https://docs.patcherctl.dev"
            )
            sys.exit(0)  # Exit to avoid running a command


# Reset
@cli.command("reset", short_help="Resets configuration based on kind.", options_metavar="<options>")
@click.argument(
    "kind",
    metavar="<reset_kind>",
    type=click.Choice(["full", "UI", "creds", "cache"], case_sensitive=False),
    required=True,
)
@click.option(
    "--credential",
    "-c",
    metavar="<credential>",
    type=click.Choice(["url", "client_id", "client_secret"], case_sensitive=False),
    help="Specify which credential to reset: URL, Client ID, or Client Secret. Defaults to all if not provided.",
)
@click.pass_context
async def reset(ctx: click.Context, kind: str, credential: str | None) -> None:
    """
    Resets configurations based on the specified kind ("full", "UI", "creds").

    \f
    **Options**:

    - ``full``: Resets credentials, UI elements, and property list file. Subsequently triggers :class:`~patcher.cli.setup.Setup` to start setup.
    - ``UI``: Resets UI elements of PDF reports (header & footer text, custom font and optional logo).
    - ``creds``: Resets credentials stored in Keychain. Useful for testing Patcher in a non-production environment first. Allows specifying which credential to reset using the ``--credential`` option.
    - ``cache``: Removes all cached data from the cache directory stored in ``~/Library/Caches/Patcher``

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: click.Context
    :param kind: Specifies the type of reset to perform.
    :type kind: str
    :param credential: The specific credential to reset when performing credentials reset. Defaults to all credentials if none specified.
    :type credential: str | None
    """
    log = ctx.obj.get("log")
    config = ctx.obj.get("config")
    ui_config = ctx.obj.get("ui_config")
    setup = ctx.obj.get("setup")
    debug = ctx.obj.get("debug")
    disable_cache = ctx.obj.get("disable_cache")

    reset_steps: list[tuple[str, Callable[[], bool]]] = [
        ("Resetting credentials...", config.reset_config),
        ("Resetting UI configuration...", ui_config.reset_config),
        ("Resetting setup state...", setup.reset_setup),
    ]

    if not disable_cache:
        data_manager = get_data_manager(ctx)
        reset_steps.append(("Clearing cached data...", data_manager.reset_cache))

    with status("Processing", enabled=not debug) as spinner:
        if kind.lower() == "full":
            log.info("Performing full reset...")

            results: list[bool] = []
            for msg, reset_method in reset_steps:
                spinner.update(msg)
                results.append(reset_method())

            if not all(results):
                failed_indices = [i for i, result in enumerate(results) if not result]
                failed_methods = [reset_steps[i][1].__name__ for i in failed_indices]
                log.error(f"Reset failed. {' '.join(failed_methods)} method(s) were unsuccessful.")
                raise PatcherError(
                    "Reset could not be completed as expected.", failed=(" ".join(failed_methods))
                )
            else:
                log.info("All resets successful. Triggering setup.")
                spinner.update("Launching setup wizard...")
                await setup.start(spinner=spinner)
        elif kind.lower() == "ui":
            log.info("Resetting UI elements...")
            spinner.update("Resetting UI configuration...")
            if ui_config.reset_config():
                spinner.update("Prompting for new UI settings...")
                await setup.prompt_ui_settings()
        elif kind.lower() == "creds":
            log.info(f"Resetting credentials... (specific: {credential if credential else 'all'})")
            spinner.update(f"Resetting credentials ({credential if credential else 'all'})...")

            # Keyring automatically overwrites existing passwords if key and service_name are the same.
            # This allows us to just call the set_credential method instead of having to delete existing
            # entries first.
            match credential:
                case "url":
                    new_url = await click.prompt("Enter your Jamf Pro URL")
                    spinner.update("Saving Jamf Pro URL to keychain...")
                    config.set_credential("URL", new_url)
                case "client_id":
                    new_client_id = await click.prompt("Enter your API Client ID")
                    spinner.update("Saving Client ID to keychain...")
                    config.set_credential("CLIENT_ID", new_client_id)
                case "client_secret":
                    new_client_secret = await click.prompt("Enter your API Client Secret")
                    spinner.update("Saving Client Secret to keychain...")
                    config.set_credential("CLIENT_SECRET", new_client_secret)
                case None:
                    log.info("Attempting to delete all credentials from keychain...")
                    cred_map = {
                        "URL": await click.prompt("Enter your Jamf Pro URL"),
                        "CLIENT_ID": await click.prompt("Enter your API Client ID"),
                        "CLIENT_SECRET": await click.prompt("Enter your API Client Secret"),
                    }
                    for k, v in cred_map.items():
                        spinner.update(f"Saving {k} to keychain...")
                        config.set_credential(k, v)
        elif kind.lower() == "cache":
            log.info("Removing cached data...")

            # Check for DataManager presence, which implies caching is enabled
            data_manager = ctx.obj.get("data_manager")
            if not data_manager:
                log.warning("Caching is disabled. No cache data to reset.")
                spinner.stop()
                console.print(
                    "⚠️ Caching is disabled. No cached data to reset.", style=WARNING_STYLE
                )
                sys.exit(0)

            spinner.update("Clearing cached data...")
            if not data_manager.reset_cache():
                raise PatcherError("Encountered an error trying to reset cache.")

    console.print("✅ Reset finished successfully.", style=SUCCESS_STYLE)


# Export
@cli.command("export", short_help="Exports patch management reports.", options_metavar="<options>")
@click.option(
    "--path",
    "-p",
    metavar="<path>",
    type=click.Path(),
    required=True,
    help="File path to save the generated report(s).",
)
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    metavar="<format>",
    type=click.Choice(["excel", "html", "pdf", "json"], case_sensitive=False),
    help="Specify report formats (default: all). Use multiple times for multiple formats.",
)
@click.option(
    "--sort",
    "-s",
    metavar="<column>",
    type=click.STRING,
    required=False,
    help="Sort patch reports by a specified column.",
)
@click.option(
    "--omit",
    "-o",
    is_flag=True,
    help="Omit software titles with patches released in last 48 hours.",
)
@click.option(
    "--date-format",
    "-d",
    metavar="<date_format>",
    type=click.Choice(list(DATE_FORMATS.keys()), case_sensitive=False),
    default="Month-Day-Year",
    help="Specify the date format for the PDF header. Choices: Month-Year, Month-Day-Year, Year-Month-Day, Day-Month-Year, Full.",
)
@click.option(
    "--ios",
    "-m",
    is_flag=True,
    help="Include the amount of enrolled mobile devices on the latest version of their respective OS.",
)
@click.option(
    "--concurrency",
    metavar="<level>",
    type=click.INT,
    default=5,
    help="Set the maximum concurrency level for API calls.",
)
@click.option(
    "--device-details",
    "-D",
    is_flag=True,
    help="Include per-title device detail sheets in Excel export (Excel format only).",
)
@click.option(
    "--homebrew/--no-homebrew",
    default=False,
    help="Also match titles against the Homebrew Cask catalog (a second matching dimension alongside Installomator). Adds a Homebrew coverage column to reports.",
)
@click.pass_context
async def export(
    ctx: click.Context,
    path: str,
    formats: tuple[str, ...],
    sort: str | None,
    omit: bool,
    date_format: str,
    ios: bool,
    concurrency: int,
    device_details: bool,
    homebrew: bool,
) -> None:
    """
    Collects patch management data from Jamf API calls and exports data to Excel and optional
    PDF formats.
    \f

    .. seealso::

        - :meth:`~patcher.cli.report.process_reports`
        - :attr:`~patcher.clients.HTTPClient.max_concurrency`
        - :ref:`export`

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: click.Context
    :param path: The path to save the generated report(s).
    :type path: str
    :param formats: If specified, will export only to the format(s) provided. Default is all formats (Excel, HTML, PDF).
    :type formats: tuple[str, ...]
    :param sort: Sort the patch reports by specifying a column.
    :type sort: str | None
    :param omit: Omit software titles with patches released in last 48 hours.
    :type omit: bool
    :param date_format: Specify the date format for the PDF header. Default is "%B %d %Y" (Month Day Year).
    :type date_format: str
    :param ios: If passed, includes iOS device data in exported reports.
    :type ios: bool
    :param concurrency: The maximum number of API requests that can be sent at once. Defaults to 5.
    :type concurrency: int
    :param device_details: If True, includes per-title device detail sheets in Excel export.
    :type device_details: bool
    :param homebrew: If True, also match titles against the Homebrew Cask catalog and add a Homebrew coverage column to reports.
    :type homebrew: bool
    """
    ui_config, plist_manager = ctx.obj.get("ui_config"), ctx.obj.get("plist_manager")

    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        concurrency=concurrency,
        disable_cache=ctx.obj.get("disable_cache"),
        debug=ctx.obj.get("debug"),
        enable_installomator=bool(plist_manager.get("enable_installomator")),
        enable_homebrew=homebrew,
        ui_config=ui_config.config,
    )
    ctx.obj["data_manager"] = patcher.data  # Store in context for analyze

    selected_formats = set(formats) if formats else {"excel", "html", "pdf", "json"}
    actual_format = DATE_FORMATS[date_format]

    # The PDF report renders header text, footer text, and (optionally) a
    # logo straight from the UI configuration. Other formats (excel,
    # html, json) don't read UI config at all. If a PDF is on the menu
    # but UI config is still at its defaults, the resulting PDF will show
    # the "Default header text" placeholders, so warn the user up front.
    if "pdf" in selected_formats:
        defaults = UIDefaults().model_dump()
        ui_at_defaults = all(
            ui_config.config.get(key) == defaults.get(key) for key in ("header_text", "footer_text")
        )
        if ui_at_defaults:
            log = ctx.obj.get("log")
            log.warning("PDF export requested with default UI configuration.")
            console.print(
                "⚠️  PDF export will use placeholder header / footer text; "
                "no UI configuration detected. Run `patcherctl reset UI` to "
                "customize, or drop pdf from --format if you only need the "
                "machine-readable formats (excel, html, json).",
                style=WARNING_STYLE,
            )

    # Status spinner + error handling are scoped inside process_reports
    await process_reports(
        patcher,
        path=path,
        formats=selected_formats,
        sort=sort,
        omit=omit,
        ios=ios,
        date_format=actual_format,
        report_title=patcher.ui_config.get("header_text"),
        enable_iom=patcher.api is not None,
        enable_homebrew=patcher.enable_homebrew,
        header_color=patcher.ui_config.get("header_color"),
        device_details=device_details,
    )


# Analyze
@cli.command(
    "analyze", short_help="Analyzes exported data by criteria.", options_metavar="<options>"
)
@click.option(
    "--excel-file",
    "-e",
    type=click.Path(exists=True),
    metavar="<file_path>",
    help="Provide path to alternate excel report. Latest exported excel report is used by default.",
)
@click.option(
    "--all-time",
    "-a",
    is_flag=True,
    help="Analyze trends across all cached data instead of a single dataset.",
)
@click.option(
    "--criteria",
    "-c",
    metavar="<filter_or_trend_criteria>",
    required=True,
    help="Filter criteria (e.g., 'most-installed').",
)
@click.option(
    "--threshold",
    "-t",
    metavar="<percentage>",
    type=float,
    default=70.0,
    help="Threshold percentage for filtering.",
)
@click.option(
    "--top-n", "-n", metavar="<int>", type=int, help="Limit the number of results displayed."
)
@click.option(
    "--min-compliance",
    metavar="<percentage>",
    type=float,
    default=None,
    help="Pre-filter: keep titles with completion_percent >= this value.",
)
@click.option(
    "--min-hosts",
    metavar="<int>",
    type=int,
    default=None,
    help="Pre-filter: keep titles with total_hosts >= this value.",
)
@click.option(
    "--released-after",
    metavar="<YYYY-MM-DD>",
    type=str,
    default=None,
    help="Pre-filter: keep titles released on or after this ISO date.",
)
@click.option("--summary", "-s", is_flag=True, help="Generate summary analysis for output.")
@click.option(
    "--output-dir",
    "-o",
    metavar="<path>",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True),
    help="Directory to save summary.",
)
@click.pass_context
async def analyze(
    ctx: click.Context,
    excel_file: str,
    criteria: str,
    threshold: float,
    top_n: int = None,
    min_compliance: float | None = None,
    min_hosts: int | None = None,
    released_after: str | None = None,
    summary: bool = False,
    output_dir: str | Path = None,
    all_time: bool = False,
) -> None:
    """
    Analyzes an Excel file with patch management data and outputs analyzed results.

    \f

    :param ctx: Context object for shared state across CLI commands.
    :type ctx: click.Context
    :param excel_file: Path to the Excel file containing patch management data.
    :type excel_file: str
    :param threshold: Filters patches below the specified completion percentage.
    :type threshold: float
    :param criteria: Specifies the criteria for filtering patches.
    :type criteria: str
    :param top_n: Number of top entries to display based on the criteria.
    :type top_n: int | None
    :param summary: Flag to generate a summary file in HTML format.
    :type summary: bool
    :param output_dir: Directory to save generated summary, only if `--summary` flag passed.
    :type output_dir: str | ~pathlib.Path | None
    :param all_time: Flag to analyze trends across all cached data.
    :type all_time: bool
    :param min_compliance: Pre-filter cutoff for ``completion_percent``.
    :type min_compliance: float | None
    :param min_hosts: Pre-filter cutoff for ``total_hosts``.
    :type min_hosts: int | None
    :param released_after: Pre-filter ISO date; keep titles released on or after.
    :type released_after: str | None
    """
    if summary and not output_dir:
        err_console.print(
            "The --summary flag requires a valid directory specified with --output-dir.",
            style=WARNING_STYLE,
        )
        return

    debug = ctx.obj.get("debug")
    ui_config = ctx.obj.get("ui_config")
    data_manager = get_data_manager(ctx)

    with status("Processing", enabled=not debug) as spinner:
        spinner.update("Loading cached patch data...")
        # NOTE: --excel-file is currently accepted but not read. Excel-to-PatchTitle
        # hydration is parked for v3.0.1.
        _ = excel_file

        if all_time:  # Analyze trends
            spinner.update(f"Calculating '{criteria}' trend across cached datasets...")
            trend_df = TrendAnalysis.apply(data_manager.get_cached_files(), criteria)

            if trend_df.empty:
                spinner.stop()
                console.print(
                    f"⚠️ No trend data available for criteria '{criteria}'.",
                    style=WARNING_STYLE,
                )
                sys.exit(0)

            spinner.update("Formatting trend results...")
            formatted_table = format_table(
                trend_df.values.tolist(), headers=trend_df.columns.tolist()
            )
            # markup=False: rendered tables contain literal brackets we must not parse as markup.
            console.print(formatted_table, markup=False)

            if summary:
                try:
                    spinner.update("Saving trend analysis report...")
                    output_file = output_dir / f"trend-analysis-{criteria}.html"
                    trend_df.to_html(output_file, index=False)
                    console.print(
                        f"✅ Trend analysis HTML saved to {output_file}.", style=SUCCESS_STYLE
                    )
                except (OSError, PermissionError, FileNotFoundError) as exc:
                    raise PatcherError(
                        "Unable to save trend analysis report as expected.",
                        dir=output_dir,
                        error_msg=str(exc),
                    )
        else:  # Filter analysis
            spinner.update(f"Filtering titles by '{criteria}'...")
            where_kwargs = {
                k: v
                for k, v in (
                    ("min_compliance", min_compliance),
                    ("min_hosts", min_hosts),
                    ("released_after", released_after),
                )
                if v is not None
            }
            filtered_titles = TitleFilter.apply(
                data_manager.titles,
                criteria,
                threshold=threshold,
                top_n=top_n,
                where=where_kwargs or None,
            )
            if len(filtered_titles) == 0:
                spinner.stop()
                console.print(
                    f"⚠️ No PatchTitle objects meet criteria {criteria}", style=WARNING_STYLE
                )
                sys.exit(0)

            spinner.update("Formatting filtered results...")
            table_data = [
                [
                    t.title,
                    t.released,
                    t.hosts_patched,
                    t.missing_patch,
                    t.latest_version,
                    t.completion_percent,
                    t.total_hosts,
                    "Y" if t.install_label else "N",
                ]
                for t in filtered_titles
            ]
            headers = [
                "Title",
                "Released",
                "Hosts Patched",
                "Missing Patch",
                "Latest Version",
                "Completion %",
                "Total Hosts",
                "Label Available (Y/N)",
            ]
            formatted_table = format_table(table_data, headers)
            console.print(formatted_table, markup=False)

        if summary and not all_time:
            try:
                spinner.update("Writing HTML summary report...")
                exported = await data_manager.export(
                    filtered_titles,
                    output_dir,
                    report_title=ui_config.config.get("header_text"),
                    analysis=True,
                    formats={"html"},
                )
            except (OSError, PermissionError, FileNotFoundError) as exc:
                raise PatcherError(
                    "Unable to save summary report as expected.", path=exported, error_msg=str(exc)
                )
            output_paths = "\n".join(list(exported.values()))
            console.print(f"✅ HTML summary saved to {output_paths}", style=SUCCESS_STYLE)


@cli.command(
    "diff",
    short_help="Compare patch state between two snapshots.",
    options_metavar="<options>",
)
@click.option(
    "--since",
    metavar="<window>",
    help="Compare against the earliest cached snapshot in the trailing window (e.g. '30d', '24h', '1w').",
)
@click.option(
    "--all-time",
    is_flag=True,
    help="Compare against the earliest cached snapshot ever. Mutually exclusive with --since.",
)
@click.option(
    "--between",
    nargs=2,
    metavar="<from-date> <to-date>",
    help="Two ISO dates (YYYY-MM-DD). Picks cached snapshots closest to each. Implies --no-fetch.",
)
@click.option(
    "--no-fetch",
    is_flag=True,
    help="Skip the live fetch; compare two cached snapshots only.",
)
@click.option(
    "--list-snapshots",
    is_flag=True,
    help="Print available cached snapshot dates and exit.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. Defaults to 'text' (terminal table). 'json' emits a structured DiffResult.",
)
@click.pass_context
async def diff(
    ctx: click.Context,
    since: str | None,
    all_time: bool,
    between: tuple[str, str] | None,
    no_fetch: bool,
    list_snapshots: bool,
    output_format: str,
) -> None:
    """
    Compare patch state between two snapshots.

    Default (no flags): compare a live fetch against the most-recent cached
    snapshot. Override with --since, --all-time, --between, or --no-fetch.

    \f

    :param ctx: Click context.
    :param since: Trailing window like ``'30d'``, ``'24h'``, ``'1w'``.
    :param all_time: Compare against earliest cached snapshot ever.
    :param between: Two ISO dates picking cached snapshots closest to each.
    :param no_fetch: Skip live fetch; compare cached snapshots only.
    :param list_snapshots: Print available cached snapshot dates and exit.
    :param output_format: ``text`` or ``json``.
    """
    debug = ctx.obj.get("debug")
    plist_manager = ctx.obj.get("plist_manager")
    ui_config = ctx.obj.get("ui_config")
    data_manager = get_data_manager(ctx)

    if list_snapshots:
        cached = sorted(data_manager.get_cached_files(), key=lambda p: p.stat().st_mtime)
        if not cached:
            err_console.print(
                "No cached snapshots. Run `patcherctl export` first to seed the cache.",
                style=WARNING_STYLE,
            )
            sys.exit(0)
        console.print("Available cached snapshots (oldest → newest):")
        for path in cached:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            console.print(f"  {mtime.isoformat(timespec='seconds')}  {path.name}")
        sys.exit(0)

    parsed_since = parse_since(since) if since else None
    parsed_between = (parse_iso_date(between[0]), parse_iso_date(between[1])) if between else None

    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        disable_cache=ctx.obj.get("disable_cache"),
        debug=ctx.obj.get("debug"),
        enable_installomator=bool(plist_manager.get("enable_installomator")),
        ui_config=ui_config.config,
    )

    with status("Processing", enabled=not debug) as spinner:
        if no_fetch or parsed_between:
            spinner.update("Comparing cached snapshots...")
        else:
            spinner.update("Fetching live patch data + comparing against cache...")

        result = await patcher.diff(
            since=parsed_since,
            all_time=all_time,
            between=parsed_between,
            no_fetch=no_fetch,
        )

    if output_format == "json":
        # print_json preserves literal brackets in the JSON (no Rich markup parsing).
        console.print_json(result.model_dump_json(indent=2))
        return

    # markup=False: rendered diff tables contain literal brackets.
    console.print(render_diff(result), markup=False)


@cli.command(
    "drift",
    short_help="Detect cross-source version drift in the Patcher catalog.",
    options_metavar="<options>",
)
@click.option(
    "--slug",
    metavar="<slug>",
    help="Show drift for a single app (e.g. 'firefox'). Excludes --vendor/--source.",
)
@click.option(
    "--vendor",
    metavar="<vendor>",
    help="Case-insensitive vendor name. Ignored when --slug is set.",
)
@click.option(
    "--source",
    metavar="<source>",
    help="Drop entries where this source did not participate (installomator or homebrew_cask). Ignored when --slug is set.",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    show_default=True,
    help="Max entries on this page. Server caps at 1000.",
)
@click.option(
    "--offset",
    type=int,
    default=0,
    show_default=True,
    help="Entries to skip before the page.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format. 'json' emits a DriftResponse or DriftEntry.",
)
@click.pass_context
async def drift(
    ctx: click.Context,
    slug: str | None,
    vendor: str | None,
    source: str | None,
    limit: int,
    offset: int,
    output_format: str,
) -> None:
    """
    Detect apps where upstream sources disagree on the current version.

    Pulls from the public Patcher catalog at ``https://api.patcherctl.dev``.
    Default mode lists every app where Installomator and Homebrew Cask
    report different versions. Use ``--slug X`` to inspect one app.

    \f

    :param ctx: Click context.
    :param slug: Single-app slug. Filters are ignored when set.
    :param vendor: Vendor filter for list mode.
    :param source: Require this source to be one of the disagreeing sources.
    :param limit: Page size.
    :param offset: Page offset.
    :param output_format: ``text`` or ``json``.
    """
    debug = ctx.obj.get("debug")
    plist_manager = ctx.obj.get("plist_manager")
    ui_config = ctx.obj.get("ui_config")

    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        disable_cache=ctx.obj.get("disable_cache"),
        debug=debug,
        enable_installomator=bool(plist_manager.get("enable_installomator")),
        ui_config=ui_config.config,
    )

    with status("Processing", enabled=not debug) as spinner:
        if slug:
            spinner.update(f"Inspecting drift for '{slug}'...")
        else:
            spinner.update("Scanning catalog for cross-source drift...")

        result = await patcher.detect_drift(
            slug=slug,
            vendor=vendor,
            source=source,
            limit=limit,
            offset=offset,
        )

    if output_format == "json":
        if result is None:
            console.print("null")
        else:
            # print_json preserves literal brackets in the JSON (no Rich markup parsing).
            console.print_json(result.model_dump_json(indent=2))
        return

    if result is None:
        console.print(f"No drift detected for '{slug}'.")
        return

    # markup=False: rendered drift tables contain literal brackets.
    if isinstance(result, DriftEntry):
        console.print(render_drift_entry(result), markup=False)
        return

    console.print(render_drift(result), markup=False)


if __name__ == "__main__":
    try:
        asyncio.run(cli())
    except APIResponseError as e:
        format_err(e)
        sys.exit(4)
    except SetupError as e:
        format_err(e)
        sys.exit(3)
    except PatcherError as e:
        format_err(e)
        sys.exit(1)
    except Exception as e:
        # Delegate to sys.excepthook
        sys.excepthook(type(e), e, e.__traceback__)
        sys.exit(2)
