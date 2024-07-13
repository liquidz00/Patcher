import asyncio
from typing import AnyStr, Optional

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
from .utils.logger import LogMe, setup_child_logger

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


@click.command()
@click.version_option(version=__version__)
@click.option("--path", "-p", type=click.Path(), required=True, help="Path to save the report")
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
async def main(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    date_format: AnyStr,
    ios: bool,
    concurrency: int,
    debug: bool,
    reset: bool,
) -> None:
    config = ConfigManager()
    token_manager = TokenManager(config)
    api_client = ApiClient(config)
    excel_report = ExcelReport()
    ui_config = UIConfigManager()
    pdf_report = PDFReport(ui_config)
    api_client.jamf_client.set_max_concurrency(concurrency=concurrency)

    log = LogMe(setup_child_logger("patcherctl", __name__, debug=debug))
    animation = Animation(enable_animation=not debug)

    setup = Setup(config=config, token_manager=token_manager, ui_config=ui_config)

    async with animation.error_handling(log):
        if reset:
            await setup.reset()
        elif not setup.completed:
            await setup.launch()

        patcher = ReportManager(
            config, token_manager, api_client, excel_report, pdf_report, ui_config, debug
        )

        actual_format = DATE_FORMATS[date_format]
        await patcher.process_reports(path, pdf, sort, omit, ios, actual_format)


if __name__ == "__main__":
    asyncio.run(main())
