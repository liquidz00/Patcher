#!/usr/local/bin/python3

import os
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
        patch_reports = await utils.get_summaries(patch_ids)

        # (option) Sort
        if sort:
            sort = sort.lower().replace(" ", "_")
            try:
                patch_reports = sorted(patch_reports, key=lambda x: x[sort])
            except KeyError:
                click.echo(f"Invalid column name for sorting: {sort}. Aborting...")
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

    except OSError as e:
        stop_event.set()
        click.echo("\n")
        os_msg = click.style(
            f"Error creating directories: {e}. Aborting...", bold=True, fg="red"
        )
        click.echo(os_msg, err=True)
        logthis.error(f"Directory could not be created. Details: {e}.")
        raise click.Abort()
    except Exception as e:
        stop_event.set()
        click.echo("\n")
        exception_msg = click.style(
            f"An error occurred: {e}. Aborting...", bold=True, fg="red"
        )
        click.echo(exception_msg, err=True)
        logthis.error(f"Unhandled exception occurred. Details: {e}")
        raise click.Abort()


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
    """Generates patch report in Excel format, with optional PDF, at the specified path"""
    stop_event = threading.Event()
    animation_thread = threading.Thread(target=animate_search, args=(stop_event,))
    animation_thread.start()

    asyncio.run(process_reports(path, pdf, sort, omit, stop_event))


if __name__ == "__main__":
    main()
