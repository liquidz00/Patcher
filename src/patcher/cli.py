import asyncio
import inspect
import sys
import warnings
from pathlib import Path
from typing import Optional, Tuple, Union

import asyncclick as click

from .__about__ import __version__
from .client.analyze import Analyzer, FilterCriteria, TrendCriteria
from .client.api_client import ApiClient
from .client.config_manager import ConfigManager
from .client.plist_manager import PropertyListManager
from .client.report_manager import ReportManager
from .client.setup import Setup
from .client.ui_manager import UIConfigManager
from .utils.animation import Animation
from .utils.data_manager import DataManager
from .utils.exceptions import APIResponseError, InstallomatorWarning, PatcherError
from .utils.logger import LogMe, PatcherLog

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}

# Context settings to enable both ``-h`` and ``--help`` for help output
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def setup_logging(debug: bool) -> None:
    """Configures global logging based on the debug flag."""
    PatcherLog.setup_logger(debug=debug)


def format_err(exc: PatcherError) -> None:
    """Formats error messages to console."""
    click.echo(click.style(f"❌ Error: {str(exc)}", fg="red", bold=True), err=True)
    click.echo(
        f"💡 For more details, please check the log file at: '{PatcherLog.LOG_FILE}'",
        err=True,
    )


def get_data_manager(ctx: click.Context) -> DataManager:
    """
    Lazily initializes and returns the shared ``DataManager`` instance.

    This ensures consistent handling of ``DataManager`` objects. Inconsistent handling of said objects could lead to inaccurate patch reports or false errors getting raised.

    :param ctx: Click context object.
    :type ctx: `click.Context <https://click.palletsprojects.com/en/stable/api/#click.Context>`_
    :return: The initialized ``DataManager`` instance.
    :rtype: :class:`~patcher.utils.data_manager.DataManager`
    """
    if "data_manager" not in ctx.obj or ctx.obj.get("data_manager") is None:
        ctx.obj["data_manager"] = DataManager(disable_cache=ctx.obj.get("disable_cache", False))
    return ctx.obj["data_manager"]


def initialize_cache(cache_dir: Path) -> None:
    """
    Ensures the cache directory exists while avoiding creating system-managed directories.

    :param cache_dir: The full path to the cache directory (e.g., ~/Library/Caches/Patcher).
    :type cache_dir: :py:obj:`~pathlib.Path`
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


sys.excepthook = PatcherLog.custom_excepthook  # Log unhandled exceptions
warnings.simplefilter("always", InstallomatorWarning)  # Show warnings in CLI
warnings.formatwarning = warning_format


# Entry
@click.group(context_settings=CONTEXT_SETTINGS, options_metavar="<options>")
@click.version_option(version=__version__)
@click.option("--debug", "-x", is_flag=True, help="Enable debug logging (verbose mode).")
@click.option(
    "--disable-cache", is_flag=True, help="Disable automatic caching of patch report data."
)
@click.pass_context
async def cli(ctx: click.Context, debug: bool, disable_cache: bool) -> None:
    """
    Main CLI entry point for Patcher.

    Visit our project documentation for full details: https://patcher.liquidzoo.io.

    \b
    Exit Codes:
        0   Success
        1   General error (e.g., PatcherError or user-facing issue)
        2   Unhandled exception
        4   API error (e.g., unauthorized, invalid response)
        130 KeyboardInterrupt (Ctrl+C)
    \f

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: `click.Context <https://click.palletsprojects.com/en/stable/api/#click.Context>`_
    :param debug: Enables debug (verbose) logging if ``True``. Defaults to ``False``.
    :type debug: :py:class:`bool`
    :param disable_cache: Disables automatic caching of patch report data if ``True``. Defaults to ``False``.
    :type disable_cache: :py:class:`bool`
    """
    setup_logging(debug)

    if not disable_cache:
        cache_dir = Path.home() / "Library/Caches/Patcher"
        initialize_cache(cache_dir)

    # Instantiate classes, store in context
    ctx.obj = {
        "debug": debug,
        "disable_cache": disable_cache,
        "animation": Animation(enable_animation=not debug),
        "log": LogMe(__name__),
        "plist_manager": PropertyListManager(),
        "config": ConfigManager(),
        "ui_config": UIConfigManager(),
    }

    setup = Setup(ctx.obj.get("config"), ctx.obj.get("ui_config"), ctx.obj.get("plist_manager"))
    ctx.obj["setup"] = setup

    # Check Setup completion
    async with ctx.obj.get("animation").error_handling():
        if ctx.obj.get("plist_manager").needs_migration():
            ctx.obj.get("plist_manager").migrate_plist()
        if not setup.completed:
            await setup.start(animator=ctx.obj.get("animation"))
            click.echo(click.style(text="Setup has completed successfully!", fg="green", bold=True))
            click.echo(
                "Patcher is now ready for use. You can use the --help flag to view available options."
            )
            click.echo("For more information, visit the project docs: https://patcher.liquidzoo.io")
            ctx.exit(0)  # Exit to avoid running a command


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
async def reset(ctx: click.Context, kind: str, credential: Optional[str]) -> None:
    """
    Resets configurations based on the specified kind ("full", "UI", "creds").

    \f
    **Options**:

    - ``full``: Resets credentials, UI elements, and property list file. Subsequently triggers :class:`~patcher.client.setup.Setup` to start setup.
    - ``UI``: Resets UI elements of PDF reports (header & footer text, custom font and optional logo).
    - ``creds``: Resets credentials stored in Keychain. Useful for testing Patcher in a non-production environment first. Allows specifying which credential to reset using the ``--credential`` option.
    - ``cache``: Removes all cached data from the cache directory stored in ``~/Library/Caches/Patcher``

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: click.Context
    :param kind: Specifies the type of reset to perform.
    :type kind: :py:class:`str`
    :param credential: The specific credential to reset when performing credentials reset. Defaults to all credentials if none specified.
    :type credential: :py:obj:`~typing.Optional` of :py:class:`str`
    """
    log = ctx.obj.get("log")
    config = ctx.obj.get("config")
    ui_config = ctx.obj.get("ui_config")
    setup = ctx.obj.get("setup")
    animation = ctx.obj.get("animation")
    disable_cache = ctx.obj.get("disable_cache")

    reset_functions = [
        config.reset_config,
        ui_config.reset_config,
        setup.reset_setup,
    ]

    if not disable_cache:
        data_manager = get_data_manager(ctx)
        reset_functions.append(data_manager.reset_cache)

    async with animation.error_handling():
        if kind.lower() == "full":
            log.info("Performing full reset...")

            # Only trigger setup if all resets successful
            results = [reset_method() for reset_method in reset_functions]

            if not all(results):
                # Notify user
                failed_indices = [i for i, result in enumerate(results) if result]
                failed_methods = [reset_functions[i].__name__ for i in failed_indices]
                log.error(f"Reset failed. {' '.join(failed_methods)} method(s) were unsuccessful.")
                raise PatcherError(
                    "Reset could not be completed as expected.", failed=(" ".join(failed_methods))
                )
            else:
                log.info("All resets successful. Triggering setup.")
                await setup.start(animation)
        elif kind.lower() == "ui":
            log.info("Resetting UI elements...")
            if ui_config.reset_config():
                # Only prompt to setup UI if reset_config was successful
                ui_config.setup_ui()
        elif kind.lower() == "creds":
            log.info(f"Resetting credentials... (specific: {credential if credential else 'all'})")

            # Keyring automatically overwrites existing passwords if key and service_name are the same.
            # This allows us to just call the set_credential method instead of having to delete existing
            # entries first.
            match credential:
                case "url":
                    new_url = click.prompt("Enter your Jamf Pro URL")
                    config.set_credential("URL", new_url)
                case "client_id":
                    new_client_id = click.prompt("Enter your API Client ID")
                    config.set_credential("CLIENT_ID", new_client_id)
                case "client_secret":
                    new_client_secret = click.prompt("Enter your API Client Secret")
                    config.set_credential("CLIENT_SECRET", new_client_secret)
                case None:
                    log.info("Attempting to delete all credentials from keychain...")
                    cred_map = {
                        "URL": click.prompt("Enter your Jamf Pro URL"),
                        "CLIENT_ID": click.prompt("Enter your API Client ID"),
                        "CLIENT_SECRET": click.prompt("Enter your API Client Secret"),
                    }
                    for k, v in cred_map.items():
                        config.set_credential(k, v)
        elif kind.lower() == "cache":
            log.info("Removing cached data...")

            # Check for DataManager presence, which implies caching is enabled
            data_manager = ctx.obj.get("data_manager")
            if not data_manager:
                log.warning("Caching is disabled. No cache data to reset.")
                click.echo(
                    click.style(
                        "⚠️ Caching is disabled. No cached data to reset.", fg="yellow", bold=True
                    )
                )
                ctx.exit(0)

            if not data_manager.reset_cache():
                raise PatcherError("Encountered an error trying to reset cache.")

    click.echo(click.style("\n✅ Reset finished successfully.", fg="green", bold=True))


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
    type=click.Choice(["excel", "html", "pdf"], case_sensitive=False),
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
@click.pass_context
async def export(
    ctx: click.Context,
    path: str,
    formats: Tuple[str, ...],
    sort: Optional[str],
    omit: bool,
    date_format: str,
    ios: bool,
    concurrency: int,
) -> None:
    """
    Collects patch management data from Jamf API calls and exports data to Excel and optional
    PDF formats.
    \f

    .. seealso::

        - :meth:`~patcher.client.report_manager.ReportManager.process_reports`
        - :meth:`~patcher.client.BaseAPIClient.concurrency`
        - :ref: `export`

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: click.Context
    :param path: The path to save the generated report(s).
    :type path: :py:class:`str`
    :param formats: If specified, will export only to the format(s) provided. Default is all formats (Excel, HTML, PDF).
    :type formats: :py:obj:`~typing.Optional` [:py:class:`str`]
    :param sort: Sort the patch reports by specifying a column.
    :type sort: :py:obj:`~typing.Optional` of :py:class:`str`
    :param omit: Omit software titles with patches released in last 48 hours.
    :type omit: :py:class:`bool`
    :param date_format: Specify the date format for the PDF header. Default is "%B %d %Y" (Month Day Year).
    :type date_format: :py:class:`str`
    :param ios: If passed, includes iOS device data in exported reports.
    :type ios: :py:class:`bool`
    :param concurrency: The maximum number of API requests that can be sent at once. Defaults to 5.
    :type concurrency: :py:class:`int`
    """
    data_manager = DataManager(disable_cache=ctx.obj.get("disable_cache"))
    ctx.obj["data_manager"] = data_manager  # Store in context for analyze

    api_client = ApiClient(config=ctx.obj.get("config"), concurrency=concurrency)

    patcher = ReportManager(
        api_client=api_client,
        data_manager=data_manager,
    )

    selected_formats = set(formats) if formats else {"excel", "html", "pdf"}
    actual_format = DATE_FORMATS[date_format]

    ui_config, plist_manager = ctx.obj.get("ui_config"), ctx.obj.get("plist_manager")

    # Not wrapping in animation error_handling in favor of existence on process_reports method
    await patcher.process_reports(
        path=path,
        formats=selected_formats,
        sort=sort,
        omit=omit,
        ios=ios,
        date_format=actual_format,
        report_title=ui_config.config.get("header_text"),
        enable_iom=plist_manager.get("enable_installomator"),
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
    summary: bool = False,
    output_dir: Union[str, Path] = None,
    all_time: bool = False,
) -> None:
    """
    Analyzes an Excel file with patch management data and outputs analyzed results.

    \f

    :param ctx: Context object for shared state across CLI commands.
    :type ctx: click.Context
    :param excel_file: Path to the Excel file containing patch management data.
    :type excel_file: :py:class:`str`
    :param threshold: Filters patches below the specified completion percentage.
    :type threshold: :py:class:`float`
    :param criteria: Specifies the criteria for filtering patches.
    :type criteria: :py:class:`str`
    :param top_n: Number of top entries to display based on the criteria.
    :type top_n: :py:class:`int`
    :param summary: Flag to generate a summary file in HTML format.
    :type summary: :py:class:`bool`
    :param output_dir: Directory to save generated summary, only if `--summary` flag passed.
    :type output_dir: :py:obj:`~typing.Union` of :py:class:`str` | :py:obj:`~pathlib.Path`
    :param all_time: Flag to analyze trends across all cached data.
    :type all_time: :py:class:`bool`
    """
    if summary and not output_dir:
        click.echo(
            click.style(
                "The --summary flag requires a valid directory specified with --output-dir.",
                fg="yellow",
            ),
            err=True,
        )
        return

    animation = ctx.obj.get("animation")
    ui_config = ctx.obj.get("ui_config")
    data_manager = get_data_manager(ctx)

    async with animation.error_handling():
        analyzer = Analyzer(
            excel_path=excel_file if excel_file else None, data_manager=data_manager
        )

        if all_time:  # Analyze trends
            trend_criteria = TrendCriteria.from_cli(criteria)

            trend_df = analyzer.timelapse(trend_criteria)

            if trend_df.empty:
                await animation.stop()
                click.echo(
                    click.style(
                        f"⚠️ No trend data available for criteria '{criteria}'.",
                        fg="yellow",
                        bold=True,
                    )
                )
                ctx.exit(0)

            formatted_table = analyzer.format_table(
                trend_df.values.tolist(), headers=trend_df.columns.tolist()
            )
            click.echo(formatted_table)

            if summary:
                try:
                    output_file = output_dir / f"trend-analysis-{criteria}.html"
                    trend_df.to_html(output_file, index=False)
                    click.echo(
                        click.style(
                            f"✅ Trend analysis HTML saved to {output_file}.", fg="green", bold=True
                        )
                    )
                except (OSError, PermissionError, FileNotFoundError) as exc:
                    raise PatcherError(
                        "Unable to save trend analysis report as expected.",
                        dir=output_dir,
                        error_msg=str(exc),
                    )
        else:  # Filter analysis
            filter_criteria = FilterCriteria.from_cli(criteria)
            filtered_titles = analyzer.filter_titles(filter_criteria, threshold, top_n)
            if len(filtered_titles) == 0:
                await animation.stop()
                click.echo(
                    click.style(
                        f"⚠️ No PatchTitle objects meet criteria {criteria}", fg="yellow", bold=True
                    ),
                    err=False,
                )
                ctx.exit(0)

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
            formatted_table = analyzer.format_table(table_data, headers)

        click.echo(formatted_table)

        if summary:
            try:
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
            click.echo(
                click.style(f"✅ HTML summary saved to {output_paths}", fg="green", bold=True)
            )


if __name__ == "__main__":
    try:
        asyncio.run(cli())
    except APIResponseError as e:
        format_err(e)
        sys.exit(4)
    except PatcherError as e:
        format_err(e)
        sys.exit(1)
    except Exception as e:
        # Delegate to sys.excepthook
        sys.excepthook(type(e), e, e.__traceback__)
        sys.exit(2)
