import asyncio
import sys
from pathlib import Path
from typing import Optional, Union

import asyncclick as click

from .__about__ import __version__
from .client.analyze import Analyzer, FilterCriteria
from .client.api_client import ApiClient
from .client.config_manager import ConfigManager
from .client.report_manager import ReportManager
from .client.setup import Setup
from .client.ui_manager import UIConfigManager
from .models.reports.excel_report import ExcelReport
from .models.reports.pdf_report import PDFReport
from .utils.animation import Animation
from .utils.exceptions import APIResponseError, PatcherError
from .utils.logger import LogMe, PatcherLog

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}

sys.excepthook = PatcherLog.custom_excepthook  # Log unhandled exceptions


def setup_logging(debug: bool) -> None:
    """Configures global logging based on the debug flag."""
    PatcherLog.setup_logger(debug=debug)


def format_err(exc: PatcherError) -> None:
    """Formats error messages to console."""
    click.echo(click.style(f"❌ Error: {str(exc)}", fg="red", bold=True), err=True)
    click.echo(
        f"💡 For more details, please check the log file at: {PatcherLog.LOG_FILE}",
        err=True,
    )


# Context settings to enable both ``-h`` and ``--help`` for help output
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


# Entry
@click.group(context_settings=CONTEXT_SETTINGS, options_metavar="<options>")
@click.version_option(version=__version__)
@click.option("--debug", "-x", is_flag=True, help="Enable debug logging (verbose mode).")
@click.pass_context
async def cli(ctx: click.Context, debug: bool) -> None:
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
    """
    setup_logging(debug)

    # Instantiate classes, store in context
    ctx.obj = {
        "debug": debug,
        "animation": Animation(enable_animation=not debug),
        "log": LogMe(__name__),
        "config": ConfigManager(),
        "ui_config": UIConfigManager(),
    }

    setup = Setup(ctx.obj.get("config"), ctx.obj.get("ui_config"))
    ctx.obj["setup"] = setup

    # Check Setup completion
    async with ctx.obj.get("animation").error_handling():
        if not setup.completed:
            await setup.start(animator=ctx.obj.get("animation"))
            click.echo(click.style(text="Setup has completed successfully!", fg="green", bold=True))
            click.echo(
                "Patcher is now ready for use. You can use the --help flag to view available options."
            )
            click.echo("For more information, visit the project docs: https://patcher.liquidzoo.io")
            # Exit to avoid running a command
            ctx.exit(0)


# Reset
@cli.command("reset", short_help="Resets configuration based on kind.", options_metavar="<options>")
@click.argument(
    "kind",
    metavar="<reset_kind>",
    type=click.Choice(["full", "UI", "creds"], case_sensitive=False),
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

    async with animation.error_handling():
        if kind.lower() == "full":
            log.info("Performing full reset...")

            reset_functions = [
                config.reset_config,
                ui_config.reset_config,
                setup.reset_setup,
            ]

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

    click.echo(click.style("✅ Reset finished successfully.", fg="green", bold=True))


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
    "--pdf",
    "-f",
    is_flag=True,
    help="Generate a PDF report along with Excel spreadsheet.",
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
    pdf: bool,
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
        - :meth:`~patcher.client.__init__.BaseAPIClient.concurrency`
        - :ref: `export`

    :param ctx: The context object, providing access to shared state between commands.
    :type ctx: click.Context
    :param path: The path to save the generated report(s).
    :type path: :py:class:`str`
    :param pdf: Specifies whether or not to generate a PDF document in addition to Excel spreadsheet.
    :type pdf: :py:class:`bool`
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
    api_client = ApiClient(config=ctx.obj.get("config"), concurrency=concurrency)
    excel_report = ExcelReport()
    pdf_report = PDFReport()

    patcher = ReportManager(
        api_client=api_client,
        excel_report=excel_report,
        pdf_report=pdf_report,
        debug=ctx.obj.get("debug"),
    )

    actual_format = DATE_FORMATS[date_format]

    # Not wrapping in animation error_handling in favor of existence on process_reports method
    await patcher.process_reports(path, pdf, sort, omit, ios, actual_format)


# Analyze
@cli.command(
    "analyze", short_help="Analyzes exported data by criteria.", options_metavar="<options>"
)
@click.argument("excel_file", metavar="<excel_file_path>", type=click.Path(exists=True))
@click.option(
    "--criteria",
    "-c",
    metavar="<filter_criteria>",
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
    "--output-dir", "-o", metavar="<path>", type=click.Path(), help="Directory to save summary."
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
    :param summary: Flag to generate a summary file.
    :type summary: :py:class:`bool`
    :param output_dir: Path to save generated summary, only if `--summary` flag passed.
    :type output_dir: :py:obj:`~typing.Union` of :py:class:`str` | :py:obj:`~pathlib.Path`
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
    async with animation.error_handling():
        analyzer = Analyzer(excel_file)
        filter_criteria = FilterCriteria.from_cli(criteria)
        filtered_titles = analyzer.filter_titles(filter_criteria, threshold, top_n)
        if len(filtered_titles) == 0:
            await animation.stop()
            click.echo(f"No PatchTitle objects meet criteria {criteria}")
            return

        table_data = [
            [
                t.title,
                t.released,
                t.hosts_patched,
                t.missing_patch,
                t.latest_version,
                t.completion_percent,
                t.total_hosts,
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
        ]
        formatted_table = analyzer.format_table(table_data, headers)

    click.echo(formatted_table)

    if summary:
        output_path = Path(output_dir) / "analysis_summary.txt"
        try:
            with open(output_path, "w") as f:
                f.write(formatted_table)
        except (OSError, PermissionError, FileNotFoundError) as exc:
            raise PatcherError(
                "Unable to save summary report as expected.", path=output_path, error_msg=str(exc)
            )
        click.echo(click.style(f"✅ Summary saved to {output_path}", fg="green", bold=True))


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
