import os
import click
import pandas as pd
import pytz
import aiohttp
import asyncio

from datetime import datetime, timedelta
from fpdf import FPDF
from dotenv import load_dotenv
from typing import List, AnyStr, Dict
from ui_config import (
    HEADER_TEXT,
    FOOTER_TEXT,
    FONT_NAME,
    FONT_REGULAR_PATH,
    FONT_BOLD_PATH,
)

# Define paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

# Load .env
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

# Set environment variables
jamf_url = os.getenv("URL")
jamf_client_id = os.getenv("CLIENT_ID")
jamf_client_secret = os.getenv("CLIENT_SECRET")
jamf_token = os.getenv("TOKEN")

# Headers for API calls
headers = {"Accept": "application/json", "Authorization": f"Bearer {jamf_token}"}


class PDF(FPDF):
    def __init__(self, orientation="L", unit="mm", format="A4"):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.add_font(FONT_NAME, "", FONT_REGULAR_PATH)
        self.add_font(FONT_NAME, "B", FONT_BOLD_PATH)

        self.table_headers = []
        self.column_widths = []

    def header(self):
        # Title in bold
        self.set_font("Assistant", "B", 24)
        self.cell(0, 10, HEADER_TEXT, new_x="LMARGIN", new_y="NEXT")

        # Month/Year in light
        self.set_font("Assistant", "", 18)
        self.cell(
            0, 10, datetime.now().strftime("%B %Y"), new_x="LMARGIN", new_y="NEXT"
        )

        if self.page_no() > 1:
            self.add_table_header()

    def add_table_header(self):
        self.set_y(30)
        self.set_font("Assistant", "B", 11)
        for header, width in zip(self.table_headers, self.column_widths):
            self.cell(width, 10, header, border=1, align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Assistant", "", 6)
        self.set_text_color(175, 175, 175)
        footer_text = f"{FOOTER_TEXT} | Page " + str(self.page_no())
        self.cell(0, 10, footer_text, 0, 0, "R")


# Convert UTC time to EST
def convert_timezone(utc_time_str: AnyStr) -> AnyStr:
    est_timezone = pytz.timezone("US/Eastern")
    utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
    est_time = utc_time.astimezone(est_timezone)
    est_time_str = est_time.strftime("%b %d %Y")

    return est_time_str


# Async API call
async def fetch_json(url, session):
    async with session.get(url, headers=headers) as response:
        return await response.json()


# Use Jamf API to retrieve all Patch titles IDs
async def get_policies() -> List:
    async with aiohttp.ClientSession() as session:
        url = f"{jamf_url}/api/v2/patch-software-title-configurations"
        response = await fetch_json(url=url, session=session)

        return [title["id"] for title in response]


# Use Jamf API to retrieve active patch summaries based upon supplied ID
async def get_summaries(policy_ids: List) -> List:
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_json(
                url=f"{jamf_url}/api/v2/patch-software-title-configurations/{policy}/patch-summary",
                session=session,
            )
            for policy in policy_ids
        ]
        summaries = await asyncio.gather(*tasks)
        return [
            {
                "software_title": summary["title"],
                "patch_released": convert_timezone(summary["releaseDate"]),
                "hosts_patched": summary["upToDate"],
                "missing_patch": summary["outOfDate"],
                "completion_percent": (
                    round(
                        (
                            summary["upToDate"]
                            / (summary["upToDate"] + summary["outOfDate"])
                        )
                        * 100,
                        2,
                    )
                    if summary["upToDate"] + summary["outOfDate"] > 0
                    else 0
                ),
                "total_hosts": summary["upToDate"] + summary["outOfDate"],
            }
            for summary in summaries
        ]


# Create excel spreadsheet with patch data for export
def export_to_excel(patch_reports: List[Dict], output_dir: AnyStr) -> AnyStr:
    column_order = [
        "software_title",
        "patch_released",
        "hosts_patched",
        "missing_patch",
        "completion_percent",
        "total_hosts",
    ]

    # create dataframe
    df = pd.DataFrame(patch_reports, columns=column_order)
    df.columns = [column.replace("_", " ").title() for column in column_order]

    # export to excel
    current_date = datetime.now().strftime("%m-%d-%y")
    excel_path = os.path.join(output_dir, f"patch-report-{current_date}.xlsx")
    df.to_excel(excel_path, index=False)

    return excel_path

# Create PDF from Excel file
def export_excel_to_pdf(excel_file: AnyStr) -> None:
    # Read excel file
    df = pd.read_excel(excel_file)

    # Create instance of FPDF
    pdf = PDF()
    pdf.table_headers = df.columns
    pdf.column_widths = [75, 40, 40, 40, 40, 40]
    pdf.add_page()
    pdf.add_table_header()

    # Data rows
    pdf.set_font(FONT_NAME, "", 9)
    for index, row in df.iterrows():
        for data, width in zip(row, pdf.column_widths):
            pdf.cell(width, 10, str(data), border=1, align="C")
        pdf.ln(10)

    # Save PDF to a file
    pdf_filename = os.path.splitext(excel_file)[0] + ".pdf"
    pdf.output(pdf_filename)


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
def main_async(path: AnyStr, pdf: bool, sort: AnyStr, omit: bool) -> None:
    """Generates patch report in Excel format, with optional PDF, at the specified path"""
    try:
        # Validate path provided is not a file
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            click.echo("Error: Provided path is a file, not a directory. Aborting...", err=True)
            raise click.Abort()

        # Ensure directories exist
        os.makedirs(output_path, exist_ok=True)
        reports_dir = os.path.join(output_path, "Patch-Reports")
        os.makedirs(reports_dir, exist_ok=True)
    except OSError as e:
        click.echo(f"Error creating directories: {e}. Aborting...", err=True)
        raise click.Abort()

    # Generate Excel report
    loop = asyncio.get_event_loop()
    patch_ids = loop.run_until_complete(get_policies())
    patch_reports = loop.run_until_complete(get_summaries(patch_ids))

    # (option) Sort
    if sort:
        sort = sort.lower().replace(" ", "_")
        try:
            patch_reports = sorted(patch_reports, key=lambda x: x[sort])
        except KeyError:
            click.echo(f"Invalid column name for sorting: {sort}. Aborting...")
            raise click.Abort()

    # (option) Omit
    if omit:
        cutoff = datetime.now() - timedelta(hours=48)
        patch_reports = [
            report
            for report in patch_reports
            if datetime.strptime(report["patch_released"], "%b %d %Y") < cutoff
        ]

    excel_file = export_to_excel(patch_reports, reports_dir)

    # (option) Export to PDF
    if pdf:
        export_excel_to_pdf(excel_file)


if __name__ == "__main__":
    main_async()
