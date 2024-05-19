import os
import aiohttp
import click
import asyncio
import threading
import time

from datetime import datetime, timedelta
from typing import AnyStr, Optional
from bin import utils, logger

logthis = logger.setup_child_logger("patcher", "cli")

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
    :param stop_event: Event to signal completion or abortion (used solely for animation).
    :type stop_event: threading.Event
    :param date_format: Format for dates in the header. Default is "%B %d %Y" (Month Day Year)
    :type date_format: AnyStr

    :return: None. Raises click.Abort on errors.
    """
    if not utils.token_valid():
        logthis.info("Bearer token is invalid, attempting refresh...")
        try:
            await utils.fetch_token()
        except Exception as token_refresh_error:
            click.echo(f"Failed to refresh token: {token_refresh_error}", err=True)
            logthis.error(f"Failed to refresh token: {token_refresh_error}")
            raise click.Abort()

    try:
        # Validate path provided is not a file
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            click.echo(
                "Error: Provided path is a file, not a directory. Aborting...", err=True
            )
            logthis.error(f"Provided path {output_path} is a file, not a directory.")
            raise click.Abort()

        # Ensure directories exist
        os.makedirs(output_path, exist_ok=True)
        reports_dir = os.path.join(output_path, "Patch-Reports")
        os.makedirs(reports_dir, exist_ok=True)

        # Async operations for patch data
        patch_ids = await utils.get_policies()
        if not patch_ids:
            click.echo("\nError obtaining patch policies. Aborting...", err=True)
            logthis.error("Policy ID API call returned an empty list.")
            raise click.Abort()
        patch_reports = await utils.get_summaries(patch_ids)
        if not patch_reports:
            click.echo("\nError establishing patch summaries. Aborting...", err=True)
            logthis.error("Error establishing patch summaries.")
            raise click.Abort()

        # (option) Sort
        if sort:
            sort = sort.lower().replace(" ", "_")
            try:
                patch_reports = sorted(patch_reports, key=lambda x: x[sort])
            except KeyError:
                stop_event.set()
                click.echo(
                    f"\nInvalid column name for sorting: {sort}. Aborting...", err=True
                )
                logthis.error(
                    f"Could not sort based on provided column ID {sort}. Column does not exist."
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
        click.echo("\n")
        if e.status == 401:
            unauth_msg = click.style(
                f"Unauthorized access detected. Please check credentials and try again. Details: {e.message}",
                bold=True,
                fg="red",
            )
            click.echo(unauth_msg, err=True)
        else:
            http_msg = click.style(
                f"Failed to retrieve data due to an HTTP error: {e.status}",
                bold=True,
                fg="red",
            )
            click.echo(http_msg, err=True)
        logthis.error(f"HTTP error occurred: {e}")
        raise click.Abort()
    except OSError as e:
        click.echo("\n")
        os_msg = click.style(
            f"Error creating directories: {e}. Aborting...", bold=True, fg="red"
        )
        click.echo(os_msg, err=True)
        logthis.error(f"Directory could not be created. Details: {e}.")
        raise click.Abort()
    except Exception as e:
        click.echo("\n")
        exception_msg = click.style(
            f"An error occurred: {e}. Aborting...", bold=True, fg="red"
        )
        click.echo(exception_msg, err=True)
        logthis.error(f"Unhandled exception occurred. Details: {e}")
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
def main(path: AnyStr, pdf: bool, sort: Optional[AnyStr], omit: bool, date_format: AnyStr) -> None:
    actual_format = DATE_FORMATS[date_format]
    stop_event = threading.Event()
    animation_thread = threading.Thread(target=animate_search, args=(stop_event,))
    animation_thread.start()

    asyncio.run(process_reports(path, pdf, sort, omit, stop_event, actual_format))


if __name__ == "__main__":
    main()
