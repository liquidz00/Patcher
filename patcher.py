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
) -> None:
    """
    Asynchronously generates and saves patch reports in Excel format at a specified
    path, with the option to also generate PDF versions. The reports can optionally
    be sorted by a specified column and filtered to omit entries based on a specific
    condition.

    :param path: The destination path where the report directory will be created.
        The function expects a directory path, not a file path. It expands user
        variables (like ~) and ensures the directory exists, creating it if necessary.
    :type path: AnyStr
    :param pdf: If True, generates PDF versions of the Excel reports.
    :type pdf: bool
    :param sort: A string specifying the column name by which to sort the reports.
        The function converts this string to lowercase and replaces spaces with
        underscores. If the column does not exist, the operation is aborted.
    :type sort: Optional[AnyStr]
    :param omit: If True, filters out reports based on a predefined condition,
        currently implemented to exclude reports with a 'patch_released' date within
        the last 48 hours.
    :type omit: bool
    :param stop_event: An event that gets set when the report generation process is
        either completed or aborted due to an error. This can be used to signal other
        parts of the application that the operation has finished.
    :type stop_event: threading.Event

    :return: None. This function does not return a value but raises a click.Abort
        exception in case of errors.
    """
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
            click.echo("\nNo policies were found. Aborting...", err=True)
            logthis.error("No patch policies were found.")
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
            utils.export_excel_to_pdf(excel_file)

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
def main(path: AnyStr, pdf: bool, sort: Optional[AnyStr], omit: bool) -> None:
    stop_event = threading.Event()
    animation_thread = threading.Thread(target=animate_search, args=(stop_event,))
    animation_thread.start()

    asyncio.run(process_reports(path, pdf, sort, omit, stop_event))


if __name__ == "__main__":
    main()
