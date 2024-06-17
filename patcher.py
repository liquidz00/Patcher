import os
import aiohttp
import click
import asyncio
import threading
import time

from datetime import datetime, timedelta
from typing import AnyStr, Optional
from bin import utils, logger, exceptions
from bin.logger import LogMe

logthis = logger.setup_child_logger("patcher", __name__)


DATE_FORMATS = {
    "Month-Year": "%B %Y",  # April 2024
    "Month-Day-Year": "%B %d %Y",  # April 21 2024
    "Year-Month-Day": "%Y %B %d",  # 2024 April 21
    "Day-Month-Year": "%d %B %Y",  # 16 April 2024
    "Full": "%A %B %d %Y",  # Thursday September 26 2013
}


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
    log = LogMe(logthis)

    with exceptions.error_handling(log, stop_event):
        # Ensure bearer token has been retrieved
        if not utils.token_valid():
            log.warn("Bearer token is invalid, attempting refresh...")
            try:
                token = await utils.fetch_token()
                if token is None:
                    raise exceptions.TokenFetchError(reason="Token refresh returned None")
            except aiohttp.ClientError as token_refresh_error:
                log.error(f"Failed to refresh token: {token_refresh_error}")
                raise exceptions.TokenFetchError(reason=token_refresh_error)

        # Ensure token has proper lifetime duration
        token_lifetime = await utils.check_token_lifetime()
        if not token_lifetime:
            log.error(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime.",
            )
            raise exceptions.TokenLifetimeError(lifetime=token_lifetime)

        # Validate path provided is not a file
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            log.error(
                f"Provided path {output_path} is a file, not a directory. Aborting...",
            )
            raise exceptions.DirectoryCreationError(path=output_path)

        # Ensure directories exist
        try:
            os.makedirs(output_path, exist_ok=True)
            reports_dir = os.path.join(output_path, "Patch-Reports")
            os.makedirs(reports_dir, exist_ok=True)
        except OSError as e:
            log.error(f"Failed to create directory: {e}")
            raise exceptions.DirectoryCreationError()

        # Async operations for patch data
        patch_ids = await utils.get_policies()
        if not patch_ids:
            log.error(
                "Policy ID API call returned an empty list. Aborting...",
            )
            raise exceptions.PolicyFetchError()
        patch_reports = await utils.get_summaries(patch_ids)
        if not patch_reports:
            log.error("Error establishing patch summaries.")
            raise exceptions.SummaryFetchError()

        # (option) Sort
        if sort:
            sort = sort.lower().replace(" ", "_")
            try:
                patch_reports = sorted(patch_reports, key=lambda x: x[sort])
            except KeyError:
                log.error(
                    f"Invalid column name for sorting: {sort.title().replace('_', ' ')}. Aborting...",
                )
                raise exceptions.SortError(column=sort.title().replace("_", " "))

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
            device_ids = await utils.get_device_ids()
            if not device_ids:
                log.error(
                    f"Received ClientError response when obtaining mobile device IDs",
                )
                raise exceptions.DeviceIDFetchError(
                    reason=f"Received ClientError response when obtaining mobile device IDs"
                )
            device_versions = await utils.get_device_os_versions(device_ids=device_ids)
            latest_versions = utils.get_sofa_feed()
            if not device_versions:
                log.error(
                    "Received empty response obtaining device OS versions from Jamf. Exiting...",
                )
                raise exceptions.DeviceOSFetchError(
                    reason="Received empty response obtaining device OS versions from Jamf."
                )
            elif not latest_versions:
                log.error("Received empty response from SOFA feed. Exiting...")
                raise exceptions.SofaFeedError(
                    reason="Received empty response from SOFA feed. Unable to verify amount of devices on latest version."
                )

            ios_data = utils.calculate_ios_on_latest(
                device_versions=device_versions, latest_versions=latest_versions
            )
            patch_reports.extend(ios_data)

        # Generate reports
        try:
            excel_file = utils.export_to_excel(patch_reports, reports_dir)
        except ValueError as e:
            log.error(f"Error exporting to excel: {e}")
            raise exceptions.ExportError(file_path=excel_file)

        if pdf:
            utils.export_excel_to_pdf(excel_file, date_format)

        stop_event.set()
        click.echo("\n")
        success_msg = click.style(
            f"Reports saved to {reports_dir}", bold=True, fg="green"
        )
        click.echo(success_msg)
        log.info(f"{len(patch_reports)} saved successfully to {reports_dir}.")


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
