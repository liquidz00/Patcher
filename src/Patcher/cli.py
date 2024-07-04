import asyncclick as click
import asyncio
import threading
import time

from typing import AnyStr, Optional
from src.Patcher.__about__ import __version__

from src.Patcher.wrappers import first_run
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher.client.ui_manager import UIConfigManager
from src.Patcher.client.token_manager import TokenManager
from src.Patcher.client.api_client import ApiClient
from src.Patcher.client.report_manager import ReportManager
from src.Patcher.model.excel_report import ExcelReport
from src.Patcher.model.pdf_report import PDFReport

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


def animate_search(stop_event: threading.Event, enable_animation: bool) -> None:
    """Animates ellipsis in 'Processing...' message."""
    if not enable_animation:
        return

    i = 0
    max_length = 0
    while not stop_event.is_set():
        message = "\rProcessing" + "." * (i % 4)
        max_length = max(max_length, len(message))
        click.echo(message, nl=False)
        i += 1
        time.sleep(0.5)

    # Clear animation line after stopping
    click.echo("\r" + " " * max_length + "\r", nl=False)


@click.command()
@click.version_option(version=__version__)
@click.option(
    "--path", "-p", type=click.Path(), required=True, help="Path to save the report"
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
@first_run
async def main(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    date_format: AnyStr,
    ios: bool,
    concurrency: int,
    debug: bool,
) -> None:
    config = ConfigManager()
    token_manager = TokenManager(config)
    api_client = ApiClient(config)
    excel_report = ExcelReport(config)
    ui_config = UIConfigManager()
    pdf_report = PDFReport(ui_config)
    api_client.jamf_client.set_max_concurrency(concurrency=concurrency)

    patcher = ReportManager(
        config, token_manager, api_client, excel_report, pdf_report, ui_config, debug
    )

    actual_format = DATE_FORMATS[date_format]
    stop_event = threading.Event()
    enable_animation = not debug
    animation_thread = threading.Thread(
        target=animate_search, args=(stop_event, enable_animation)
    )
    animation_thread.start()

    await patcher.process_reports(path, pdf, sort, omit, ios, stop_event, actual_format)


if __name__ == "__main__":
    asyncio.run(main())
