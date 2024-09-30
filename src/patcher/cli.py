import asyncio
from typing import Optional

import asyncclick as click

from .__about__ import __version__
from .client.api_client import ApiClient
from .client.config_manager import ConfigManager
from .client.report_manager import ReportManager
from .client.setup import Setup
from .client.token_manager import TokenManager
from .client.ui_manager import UIConfigManager
from .models.reports.excel_report import ExcelReport
from .models.reports.pdf_report import PDFReport
from .utils.animation import Animation
from .utils.logger import LogMe

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


@click.command()
@click.version_option(version=__version__)
@click.option(
    "--path",
    "-p",
    type=click.Path(),
    required=False,  # Defaulting to false in favor of `--reset`
    help="Path to save the report(s)",
)
@click.option(
    "--pdf",
    "-f",
    is_flag=True,
    help="Generate a PDF report along with Excel spreadsheet",
)
@click.option(
    "--sort",
    "-s",
    type=click.STRING,
    required=False,
    help="Sort patch reports by a specified column.",
)
@click.option(
    "--omit",
    "-o",
    is_flag=True,
    help="Omit software titles with patches released in last 48 hours",
)
@click.option(
    "--date-format",
    "-d",
    type=click.Choice(list(DATE_FORMATS.keys()), case_sensitive=False),
    default="Month-Day-Year",
    help="Specify the date format for the PDF header from predefined choices.",
)
@click.option(
    "--ios",
    "-m",
    is_flag=True,
    help="Include the amount of enrolled mobile devices on the latest version of their respective OS.",
)
@click.option(
    "--concurrency",
    type=click.INT,
    default=5,
    help="Set the maximum concurrency level for API calls.",
)
@click.option(
    "--debug",
    "-x",
    is_flag=True,
    default=False,
    help="Enable debug logging to see detailed debug messages.",
)
@click.option(
    "--reset",
    "-r",
    is_flag=True,
    default=False,
    help="Resets the setup process and triggers the setup assistant again.",
)
@click.pass_context
async def main(
    ctx: click.Context,
    path: str,
    pdf: bool,
    sort: Optional[str],
    omit: bool,
    date_format: str,
    ios: bool,
    concurrency: int,
    debug: bool,
    reset: bool,
) -> None:
    if not ctx.params["reset"] and not ctx.params["path"]:
        raise click.UsageError("The --path option is required unless --reset is specified.")

    log = LogMe(__name__, debug=debug)
    animation = Animation(enable_animation=not debug)

    config = ConfigManager()
    ui_config = UIConfigManager()

    setup = Setup(config=config, ui_config=ui_config)

    async with animation.error_handling(log):
        if not setup.completed:
            await setup.prompt_method(animator=animation)
            click.echo(click.style(text="Setup has completed successfully!", fg="green", bold=True))
            click.echo("Patcher is now ready for use.")
            click.echo("You can use the --help flag to view available options.")
            click.echo("For more information, visit the project docs: https://patcher.liquidzoo.io")
            return
        elif reset:
            await animation.update_msg("Resetting elements...")
            await setup.reset()
            click.echo(click.style(text="Reset has completed as expected!", fg="green", bold=True))
            return

        api_client = ApiClient(config, concurrency)
        token_manager = TokenManager(config)
        excel_report = ExcelReport()
        pdf_report = PDFReport(ui_config)
        api_client.set_concurrency(concurrency=concurrency)

        patcher = ReportManager(
            config, token_manager, api_client, excel_report, pdf_report, ui_config, debug
        )

        actual_format = DATE_FORMATS[date_format]
        await patcher.process_reports(path, pdf, sort, omit, ios, actual_format)


if __name__ == "__main__":
    asyncio.run(main())
