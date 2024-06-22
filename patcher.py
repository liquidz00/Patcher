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
from bin.globals import JAMF_TOKEN_EXPIRATION

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


async def process_reports(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    ios: bool,
    stop_event: threading.Event,
    date_format: AnyStr = "%B %d %Y",
    debug: bool = False,
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
    :param debug: Enable debug logging if True.
    :type debug: bool

    :return: None. Raises click.Abort on errors.
    """
    # Log all the things
    logthis = logger.setup_child_logger("patcher", __name__, debug=debug)
    log = LogMe(logthis, stop_event=stop_event)
    log.debug("Beginning Patcher process...")

    with exceptions.error_handling(log, stop_event):
        # Ensure bearer token has been retrieved
        log.debug("Checking bearer token validity")
        if not utils.token_valid():
            log.warn("Bearer token is invalid, attempting refresh...")
            try:
                token = await utils.fetch_token()
                if token is None:
                    log.error("Token refresh returned None")
                    raise exceptions.TokenFetchError(
                        reason="Token refresh returned None"
                    )
                else:
                    log.info("Token successfully refreshed.")
            except aiohttp.ClientError as token_refresh_error:
                log.error(f"Failed to refresh token: {token_refresh_error}")
                raise exceptions.TokenFetchError(reason=token_refresh_error)
        else:
            log.debug("Bearer token passed validity checks.")

        # Ensure token has proper lifetime duration
        log.debug("Verifying token lifetime is greater than 5 minutes")
        try:
            token_lifetime = await utils.check_token_lifetime()
            log.info("Token lifetime verified successfully.")
        except aiohttp.ClientResponseError as e:
            log.error(
                f"Received unauthorized response checking token lifetime. API client may not have sufficient privileges."
            )
            raise exceptions.APIPrivilegeError(reason=e)
        if not token_lifetime:
            log.error(
                "Bearer token lifetime is too short. Review the Patcher Wiki for instructions to increase the token's lifetime.",
            )
            raise exceptions.TokenLifetimeError(lifetime=JAMF_TOKEN_EXPIRATION)
        else:
            log.debug("Token lifetime is at least 5 minutes. Continuing...")

        # Validate path provided is not a file
        log.debug("Validating path provided is not a file...")
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            log.error(
                f"Provided path {output_path} is a file, not a directory. Aborting...",
            )
            raise exceptions.DirectoryCreationError(path=output_path)
        else:
            log.debug(f"Output path '{output_path}' is valid.")

        # Ensure directories exist
        log.debug("Attempting to create directories if they do not already exist...")
        try:
            os.makedirs(output_path, exist_ok=True)
            reports_dir = os.path.join(output_path, "Patch-Reports")
            os.makedirs(reports_dir, exist_ok=True)
            log.info(f"Reports directory created at '{reports_dir}'.")
        except OSError as e:
            log.error(f"Failed to create directory: {e}")
            raise exceptions.DirectoryCreationError()

        # Async operations for patch data
        log.debug("Attempting to retrieve policy IDs.")
        patch_ids = await utils.get_policies()
        if not patch_ids:
            log.error(
                "Policy ID API call returned an empty list. Aborting...",
            )
            raise exceptions.PolicyFetchError()
        log.debug(f"Retrieved policy IDs for {len(patch_ids)} policies.")
        log.debug("Attempting to retrieve patch summaries.")
        patch_reports = await utils.get_summaries(patch_ids)
        if not patch_reports:
            log.error("Error establishing patch summaries.")
            raise exceptions.SummaryFetchError()
        else:
            log.debug(f"Received policy summaries for {len(patch_reports)} policies.")

        # (option) Sort
        if sort:
            log.debug(f"Detected sorting option '{sort}'")
            sort = sort.lower().replace(" ", "_")
            try:
                patch_reports = sorted(patch_reports, key=lambda x: x[sort])
                log.debug(f"Patch reports sorted by '{sort}'.")
            except KeyError:
                log.error(
                    f"Invalid column name for sorting: {sort.title().replace('_', ' ')}. Aborting...",
                )
                raise exceptions.SortError(column=sort.title().replace("_", " "))

        # (option) Omit
        if omit:
            log.debug(
                f"Detected omit flag set to {omit}. Omitting policies with patches released in past 48 hours."
            )
            cutoff = datetime.now() - timedelta(hours=48)
            original_count = len(patch_reports)
            patch_reports = [
                report
                for report in patch_reports
                if datetime.strptime(report["patch_released"], "%b %d %Y") < cutoff
            ]
            omitted_count = original_count - len(patch_reports)
            log.debug(f"Omitted {omitted_count} policies with recent patches.")

        # (option) iOS
        if ios:
            log.debug(
                f"Detected ios flag set to {ios}. Including iOS information in reports."
            )
            log.debug("Attempting to fetch mobile device IDs.")
            device_ids = await utils.get_device_ids()
            if not device_ids:
                log.error(
                    f"Received ClientError response when obtaining mobile device IDs",
                )
                raise exceptions.DeviceIDFetchError(
                    reason=f"Received ClientError response when obtaining mobile device IDs"
                )

            log.debug(f"Obtained device IDs for {len(device_ids)} devices.")
            log.debug(
                "Attempting to retrieve operating system versions for each device."
            )
            device_versions = await utils.get_device_os_versions(device_ids=device_ids)
            log.debug(
                "Retrieving latest iOS version information from SOFA feed (https://sofa.macadmins.io)"
            )
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

            log.debug(
                "Retrieved device version info and SOFA feed as expected. Calculating devices on latest version."
            )
            ios_data = utils.calculate_ios_on_latest(
                device_versions=device_versions, latest_versions=latest_versions
            )
            log.debug("Appending iOS device information to dataframe...")
            patch_reports.extend(ios_data)
            log.debug("iOS information successfully appended to patch reports.")

        # Generate reports
        log.debug("Generating excel file...")
        try:
            excel_file = utils.export_to_excel(patch_reports, reports_dir)
            log.debug(f"Excel file generate successfully at '{excel_file}'.")
        except ValueError as e:
            log.error(f"Error exporting to excel: {e}")
            raise exceptions.ExportError(file_path=excel_file)

        if pdf:
            log.debug(f"Detected PDF flag set to {pdf}. Generating PDF file...")
            try:
                utils.export_excel_to_pdf(excel_file, date_format)
                log.debug("PDF file generated successfully.")
            except (OSError, PermissionError) as e:
                log.error(f"Error generating PDF file. Check file permissions: {e}")
                raise exceptions.ExportError(file_path=excel_file)
            except Exception as e:
                log.error(f"Unhandled error encountered: {e}")
                raise exceptions.ExportError()

        stop_event.set()
        log.debug(
            "Patcher finished as expected. Additional logs can be found at '~/Patcher/Logs'."
        )
        log.info(
            f"{len(patch_reports)} patch reports saved successfully to {reports_dir}."
        )
        success_msg = click.style(
            f"\rSuccess! Reports saved to {reports_dir}", bold=True, fg="green"
        )
        click.echo(success_msg)


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
@click.option(
    "--debug",
    "-x",
    is_flag=True,
    default=False,
    help="Enable debug logging to see detailed debug messages.",
)
def main(
    path: AnyStr,
    pdf: bool,
    sort: Optional[AnyStr],
    omit: bool,
    ios: bool,
    date_format: AnyStr,
    debug: bool,
) -> None:
    actual_format = DATE_FORMATS[date_format]
    stop_event = threading.Event()
    enable_animation = not debug
    animation_thread = threading.Thread(
        target=animate_search, args=(stop_event, enable_animation)
    )
    animation_thread.start()

    asyncio.run(
        process_reports(path, pdf, sort, omit, ios, stop_event, actual_format, debug)
    )


if __name__ == "__main__":
    main()
