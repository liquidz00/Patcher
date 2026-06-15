"""
The ``patcherctl`` command-line interface.

The asyncclick entry point and every subcommand (``export``, ``analyze``,
``diff``, ``drift``, ``reset``). Terminal output lives in
:mod:`patcher.cli._console`; orchestration helpers in :mod:`patcher.cli._helpers`.
"""

import asyncio
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import asyncclick as click
import rich.traceback

from ..__about__ import __version__
from ..clients.patcher_api import DriftEntry
from ..core.config_manager import ConfigManager
from ..core.exceptions import APIResponseError, PatcherError, SetupError
from ..core.logger import LogMe
from ..core.models.settings import PatcherSettings, UIDefaults
from ..core.patcher_client import PatcherClient
from ._console import (
    SUCCESS_STYLE,
    WARNING_STYLE,
    build_fleet_summary,
    build_table,
    completion_text,
    console,
    err_console,
    format_err,
    render_diff,
    render_drift,
    render_drift_entry,
    setup_logging,
    status,
)
from ._helpers import (
    _install_cli_process_hooks,
    get_data_manager,
    initialize_cache,
    parse_iso_date,
    parse_since,
    process_reports,
)
from .setup import Setup

# show_locals=False keeps pasted tracebacks token-safe; suppress collapses asyncclick's own frames.
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

    # All three creds present (flags or env) means non-interactive: skip the keychain and prompts.
    noninteractive = bool(client_id and client_secret and url)

    config_manager = ConfigManager(in_memory_credentials={}) if noninteractive else ConfigManager()

    # Instantiate classes, store in context
    ctx.obj = {
        "debug": debug,
        "disable_cache": disable_cache,
        "noninteractive": noninteractive,
        "log": LogMe(__name__),
        "settings": PatcherSettings.load(),
        "config": config_manager,
    }

    setup = Setup(ctx.obj.get("config"), ctx.obj.get("settings"))
    ctx.obj["setup"] = setup

    # Check Setup completion
    with status("Processing", enabled=not debug) as spinner:
        # Interpreter mismatch warns, doesn't block: keychain writes may fail (errSecInvalidOwnerEdit) but reads work. See #68.
        if not noninteractive and setup.completed and not fresh:
            recorded_interpreter = ctx.obj.get("settings").interpreter_path
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
    setup = ctx.obj.get("setup")
    debug = ctx.obj.get("debug")
    disable_cache = ctx.obj.get("disable_cache")

    reset_steps: list[tuple[str, Callable[[], bool]]] = [
        ("Resetting credentials...", config.reset_config),
        ("Resetting UI configuration...", setup.reset_ui_config),
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
            if setup.reset_ui_config():
                spinner.stop()  # prompt_ui_settings prompts; a live spinner swallows input
                await setup.prompt_ui_settings()
        elif kind.lower() == "creds":
            log.info(f"Resetting credentials... (specific: {credential if credential else 'all'})")
            spinner.update(f"Resetting credentials ({credential if credential else 'all'})...")
            spinner.stop()  # prompts below can't run under a live spinner (input hangs)

            # Keyring overwrites on a matching key+service, so no delete-first is needed.
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
                    new_client_secret = await click.prompt(
                        "Enter your API Client Secret", hide_input=True
                    )
                    spinner.update("Saving Client Secret to keychain...")
                    config.set_credential("CLIENT_SECRET", new_client_secret)
                case None:
                    log.info("Attempting to delete all credentials from keychain...")
                    cred_map = {
                        "URL": await click.prompt("Enter your Jamf Pro URL"),
                        "CLIENT_ID": await click.prompt("Enter your API Client ID"),
                        "CLIENT_SECRET": await click.prompt(
                            "Enter your API Client Secret", hide_input=True
                        ),
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
    help="Also match titles against the Homebrew Cask catalog (a second matching dimension alongside Installomator). Coverage surfaces in analyze and JSON exports, not rendered reports.",
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

        - :meth:`~patcher.cli._helpers.process_reports`
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
    :param homebrew: If True, also match titles against the Homebrew Cask catalog. Coverage surfaces in analyze and JSON exports, not rendered reports.
    :type homebrew: bool
    """
    settings = ctx.obj.get("settings")

    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        concurrency=concurrency,
        disable_cache=ctx.obj.get("disable_cache"),
        debug=ctx.obj.get("debug"),
        enable_matching=settings.enable_matching,
        enable_homebrew=homebrew,
        integrations=settings.integrations,
        ui_config=settings.user_interface_settings.model_dump(),
        ignored_titles=settings.ignored_titles,
    )

    selected_formats = set(formats) if formats else {"excel", "html", "pdf", "json"}
    actual_format = DATE_FORMATS[date_format]

    # PDF is the only format that reads UI config; warn if it's still at defaults (placeholder text).
    if "pdf" in selected_formats:
        defaults = UIDefaults().model_dump()
        ui_at_defaults = all(
            getattr(settings.user_interface_settings, key) == defaults.get(key)
            for key in ("header_text", "footer_text")
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
    help="Analyze a previously-exported Excel report instead of the cached patch data.",
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
    settings = ctx.obj.get("settings")
    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        disable_cache=ctx.obj.get("disable_cache"),
        debug=debug,
        enable_matching=settings.enable_matching,
        ui_config=settings.user_interface_settings.model_dump(),
        ignored_titles=settings.ignored_titles,
    )

    if excel_file and all_time:
        raise PatcherError(
            "--excel-file cannot be combined with --all-time; trend analysis needs cached snapshots."
        )

    with status("Processing", enabled=not debug) as spinner:
        spinner.update(
            "Loading patch data from Excel..." if excel_file else "Loading cached patch data..."
        )

        # Spinner wraps the work only (compute + file writes); results render below.
        summary_path = None
        if all_time:  # Analyze trends
            spinner.update(f"Calculating '{criteria}' trend across cached datasets...")
            save_to = output_dir / f"trend-analysis-{criteria}.html" if summary else None
            try:
                trend_df = await patcher.analyze_trend(criteria, save_to=save_to)
            except (OSError, PermissionError, FileNotFoundError) as exc:
                raise PatcherError(
                    "Unable to save trend analysis report as expected.",
                    dir=output_dir,
                    error_msg=str(exc),
                )
            summary_path = save_to if (summary and not trend_df.empty) else None
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
            if excel_file:
                filtered_titles = await patcher.analyze_excel(
                    excel_file,
                    criteria,
                    threshold=threshold,
                    top_n=top_n,
                    where=where_kwargs or None,
                )
            else:
                filtered_titles = await patcher.analyze(
                    patcher.data.titles,
                    criteria,
                    threshold=threshold,
                    top_n=top_n,
                    where=where_kwargs or None,
                )

            if summary and len(filtered_titles) > 0:
                spinner.update("Writing HTML summary report...")
                try:
                    exported = await patcher.export(
                        filtered_titles,
                        output_dir=output_dir,
                        report_title=settings.user_interface_settings.header_text,
                        analysis=True,
                        formats={"html"},
                    )
                except (OSError, PermissionError, FileNotFoundError) as exc:
                    raise PatcherError(
                        "Unable to save summary report as expected.",
                        path=output_dir,
                        error_msg=str(exc),
                    )
                summary_path = "\n".join(list(exported.values()))

    if all_time:
        if trend_df.empty:
            console.print(
                f"⚠️ No trend data available for criteria '{criteria}'.", style=WARNING_STYLE
            )
            sys.exit(0)
        console.print(build_table(trend_df.values.tolist(), headers=trend_df.columns.tolist()))
        if summary_path is not None:
            console.print(f"✅ Trend analysis HTML saved to {summary_path}.", style=SUCCESS_STYLE)
    else:
        if len(filtered_titles) == 0:
            console.print(f"⚠️ No PatchTitle objects meet criteria {criteria}", style=WARNING_STYLE)
            sys.exit(0)

        console.print(build_fleet_summary(patcher.data.titles, threshold))

        table_data = [
            [
                t.title,
                t.released,
                t.hosts_patched,
                t.missing_patch,
                t.latest_version,
                completion_text(t.completion_percent, threshold),
                t.total_hosts,
                "Y" if t.installomator else "N",
            ]
            for t in filtered_titles
        ]
        headers = [
            "Title",
            "Released",
            "Patched",
            "Missing",
            "Version",
            "Completion %",
            "Total",
            "Label",
        ]
        justify = ["left", "left", "right", "right", "left", "right", "right", "center"]
        caption = (
            f"criteria={criteria}  ·  "
            f"showing {len(filtered_titles)} of {len(patcher.data.titles)} titles"
        )
        console.print(
            build_table(table_data, headers, caption=caption, justify=justify, lines=True)
        )
        if summary_path is not None:
            console.print(f"✅ HTML summary saved to {summary_path}", style=SUCCESS_STYLE)


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
    settings = ctx.obj.get("settings")
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
        enable_matching=settings.enable_matching,
        ui_config=settings.user_interface_settings.model_dump(),
        ignored_titles=settings.ignored_titles,
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

    console.print(render_diff(result))


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
    settings = ctx.obj.get("settings")

    patcher = PatcherClient(
        config=ctx.obj.get("config"),
        disable_cache=ctx.obj.get("disable_cache"),
        debug=debug,
        enable_matching=settings.enable_matching,
        ui_config=settings.user_interface_settings.model_dump(),
        ignored_titles=settings.ignored_titles,
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

    if isinstance(result, DriftEntry):
        console.print(render_drift_entry(result))
        return

    console.print(render_drift(result))


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
