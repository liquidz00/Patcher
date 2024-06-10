import os
import aiohttp
import click
import asyncio
import threading
import time

from enum import Enum
from datetime import datetime, timedelta
from typing import AnyStr, Optional
from bin import utils, logger

logthis = logger.setup_child_logger("patcher", __name__)

DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


class LogMe:
    class Level(Enum):
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"

    def __init__(self):
        self.INFO = logthis.info
        self.WARNING = logthis.warning
        self.ERROR = logthis.error

    def __call__(self, msg: AnyStr, level: "LogMe.Level"):
        self._inform(msg, level)

    def _inform(self, msg: AnyStr, level: "LogMe.Level" = "LogMe.Level.INFO"):
        match level:
            case self.Level.INFO:
                self.INFO(f"\n{msg}")
                std_output = click.style(text=f"\n{msg}", bold=False)
                click.echo(message=std_output, err=False)
            case self.Level.WARNING:
                self.WARNING(f"\n{msg}")
                warn_output = click.style(text=f"\n{msg}", fg="yellow", bold=True)
                click.echo(warn_output, err=False)
            case self.Level.ERROR:
                self.ERROR(f"\n{msg}")
                err_output = click.style(text=f"\n{msg}", fg="red", bold=True)
                click.echo(err_output, err=True)


def animate_search(stop_event: threading.Event) -> None:
    """Animates ellipsis in 'Processing...' message."""
    i = 0
    max_length = 0
    while not stop_event.is_set():
        message = "\rProcessing" + "." * (i % 4)
        max_length = max(max_length, len(message))
        click.echo(message, nl=False)
        i += 1
        time.sleep(0.5)


async def process_reports(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    ios: bool,
    stop_event: threading.Event,
    date_format: AnyStr = "%B %d %Y",
) -> None:
    """
    Asynchronously generates and saves patch reports in Excel format at the specified path,
    optionally generating PDF versions, sorting by a specified column, and omitting recent entries.

    :param path: Directory path to save the reports
    :type path: AnyStr
    :param pdf: Generate PDF versions of the reports if True.
    :type pdf: bool
    :param sort: Column name to sort the reports.
    :type sort: Optional[AnyStr]
    :param omit: Omit reports based on a condition if True.
    :type omit: bool
    :param ios: Include iOS device data if True
    :type ios: bool
    :param stop_event: Event to signal completion or abortion (used solely for animation).
    :type stop_event: threading.Event
    :param date_format: Format for dates in the header. Default is "%B %d %Y" (Month Day Year)
    :type date_format: AnyStr

    :return: None. Raises click.Abort on errors.
    """
    # Log all the things
    log_me = LogMe()

    try:
        # Ensure bearer token has been retrieved
        if not utils.token_valid():
            log_me("Bearer token is invalid, attempting refresh...", LogMe.Level.INFO)
            try:
                await utils.fetch_token()
            except Exception as token_refresh_error:
                log_me(f"Failed to refresh token: {token_refresh_error}", LogMe.Level.ERROR)
                raise click.Abort()

        # Ensure token has proper lifetime duration
        token_lifetime = await utils.check_token_lifetime()
        if not token_lifetime:
            log_me(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime.",
                LogMe.Level.ERROR,
            )
            raise click.Abort()

        # Validate path provided is not a file
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            log_me(
                f"Provided path {output_path} is a file, not a directory. Aborting...",
                LogMe.Level.ERROR,
            )
            raise click.Abort()

        # Ensure directories exist
        os.makedirs(output_path, exist_ok=True)
        reports_dir = os.path.join(output_path, "Patch-Reports")
        os.makedirs(reports_dir, exist_ok=True)

        # Async operations for patch data
        patch_ids = await utils.get_policies()
        if not patch_ids:
            log_me(
                "Policy ID API call returned an empty list. Aborting...",
                LogMe.Level.ERROR,
            )
            raise click.Abort()
        patch_reports = await utils.get_summaries(patch_ids)
        if not patch_reports:
            log_me("Error establishing patch summaries.", LogMe.Level.ERROR)
            raise click.Abort()

        # (option) Sort
        if sort:
            sort = sort.lower().replace(" ", "_")
            try:
                patch_reports = sorted(patch_reports, key=lambda x: x[sort])
            except KeyError:
                stop_event.set()
                log_me(
                    f"Invalid column name for sorting: {sort}. Aborting...",
                    LogMe.Level.ERROR,
                )
                raise click.Abort()

        # (option) Omit
        if omit:
            cutoff = datetime.now() - timedelta(hours=48)
            patch_reports = [
                report
                for report in patch_reports
                if datetime.strptime(report["patch_released"], "%b %d %Y") < cutoff
            ]

        # (option) iOS
        if ios:
            try:
                device_ids = await utils.get_device_ids()
            except aiohttp.ClientError as e:
                log_me(
                    f"Received ClientError response when obtaining mobile device IDs: {e}",
                    LogMe.Level.ERROR,
                )
                raise click.Abort()
            device_versions = await utils.get_device_os_versions(device_ids=device_ids)
            latest_versions = utils.get_sofa_feed()
            if not device_versions and not latest_versions:
                log_me(
                    "Received empty response obtaining device versions or SOFA feed. Exiting...",
                    LogMe.Level.ERROR,
                )
                raise click.Abort()

            ios_data = utils.calculate_ios_on_latest(
                device_versions=device_versions, latest_versions=latest_versions
            )
            patch_reports.extend(ios_data)

        # Generate reports
        excel_file = utils.export_to_excel(patch_reports, reports_dir)
        if pdf:
            utils.export_excel_to_pdf(excel_file, date_format)

        stop_event.set()
        click.echo("\n")
        success_msg = click.style(
            f"Reports saved to {reports_dir}", bold=True, fg="green"
        )
        click.echo(success_msg)

    except aiohttp.ClientResponseError as e:
        if e.status == 401:
            log_me(
                f"Unauthorized access detected. Please check credentials and try again. Details: {e.message}",
                LogMe.Level.ERROR,
            )
        else:
            log_me(
                f"Failed to retrieve data due to an HTTP error: {e.status}",
                LogMe.Level.ERROR,
            )
        raise click.Abort()
    except OSError as e:
        log_me(f"Error creating directories: {e}. Aborting...", LogMe.Level.ERROR)
        raise click.Abort()
    except Exception as e:
        log_me(f"An unexpected error occurred: {e}. Aborting...", LogMe.Level.ERROR)
        raise click.Abort()
    finally:
        # Ensure animation stops regardless of error
        stop_event.set()


@click.command()
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
def main(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    ios: bool,
    date_format: AnyStr,
) -> None:
    actual_format = DATE_FORMATS[date_format]
    stop_event = threading.Event()
    animation_thread = threading.Thread(target=animate_search, args=(stop_event,))
    animation_thread.start()

    asyncio.run(process_reports(path, pdf, sort, omit, ios, stop_event, actual_format))


if __name__ == "__main__":
    main()
