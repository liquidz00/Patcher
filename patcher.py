#!/usr/local/bin/python3

import os
import click
import asyncio

from datetime import datetime, timedelta
from typing import AnyStr
from bin import utils, logger

logthis = logger.setup_child_logger("patcher", "cli")


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
def main(path: AnyStr, pdf: bool, sort: AnyStr, omit: bool) -> None:
    """Generates patch report in Excel format, with optional PDF, at the specified path"""
    try:
        # Validate path provided is not a file
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            click.echo(
                "Error: Provided path is a file, not a directory. Aborting...", err=True
            )
            logthis.info(f"Provided path {output_path} is a file, not a directory.")
            raise click.Abort()

        # Ensure directories exist
        os.makedirs(output_path, exist_ok=True)
        reports_dir = os.path.join(output_path, "Patch-Reports")
        os.makedirs(reports_dir, exist_ok=True)
    except OSError as e:
        click.echo(f"Error creating directories: {e}. Aborting...", err=True)
        logthis.info(f"Directory could not be created. Details: {e}.")
        raise click.Abort()

    # Generate Excel report
    loop = asyncio.get_event_loop()
    patch_ids = loop.run_until_complete(utils.get_policies())
    patch_reports = loop.run_until_complete(utils.get_summaries(patch_ids))

    # (option) Sort
    if sort:
        sort = sort.lower().replace(" ", "_")
        try:
            patch_reports = sorted(patch_reports, key=lambda x: x[sort])
        except KeyError:
            click.echo(f"Invalid column name for sorting: {sort}. Aborting...")
            logthis.info(f"Could not sort based on provided column ID {sort}. Column does not exist.")
            raise click.Abort()

    # (option) Omit
    if omit:
        cutoff = datetime.now() - timedelta(hours=48)
        patch_reports = [
            report
            for report in patch_reports
            if datetime.strptime(report["patch_released"], "%b %d %Y") < cutoff
        ]

    excel_file = utils.export_to_excel(patch_reports, reports_dir)

    # (option) Export to PDF
    if pdf:
        utils.export_excel_to_pdf(excel_file)


if __name__ == "__main__":
    main()
