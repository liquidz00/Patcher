import os
import pandas as pd
import aiohttp
import asyncio

from bin import logger, globals
from datetime import datetime, timedelta, timezone
from fpdf import FPDF
from dotenv import load_dotenv, set_key
from typing import List, AnyStr, Dict, Optional
from ui_config import (
    HEADER_TEXT,
    FOOTER_TEXT,
    FONT_NAME,
    FONT_REGULAR_PATH,
    FONT_BOLD_PATH,
)

# Define paths
BASE_DIR = globals.BIN_DIR
ROOT_DIR = globals.ROOT_DIR
FONTS_DIR = globals.FONT_DIR
ENV_PATH = globals.ENV_PATH

# Load .env
load_dotenv(dotenv_path=ENV_PATH)

# Set environment variables
jamf_url = os.getenv("URL")
jamf_client_id = os.getenv("CLIENT_ID")
jamf_client_secret = os.getenv("CLIENT_SECRET")
jamf_token = os.getenv("TOKEN")

# Headers for API calls
headers = {"Accept": "application/json", "Authorization": f"Bearer {jamf_token}"}

# Logging
logthis = logger.setup_child_logger("patcher", __name__)


class PDF(FPDF):
    def __init__(self, orientation="L", unit="mm", format="A4", date_format="%B %d %Y"):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.date_format = date_format

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
            0,
            10,
            datetime.now().strftime(self.date_format),
            new_x="LMARGIN",
            new_y="NEXT",
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


# Format UTC time
def convert_timezone(utc_time_str: AnyStr) -> AnyStr:
    """
    Converts a UTC time string to a formatted string without timezone information.

    :param utc_time_str: UTC time string in ISO 8601 format.
    :type utc_time_str: AnyStr
    :return: Formatted time string or error message.
    :rtype: AnyStr
    """
    try:
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S%z")
        time_str = utc_time.strftime("%b %d %Y")
        return time_str
    except ValueError as e:
        logthis.warn(f"Invalid time format provided. Details: {e}")
        return "Invalid time format"
    except Exception as e:
        logthis.error(f"An unexpected error occurred: {e}")
        return "Conversion error."


# Update Bearer Token in .env
def update_env(token: AnyStr, expires_in: int) -> None:
    """
    Updates the TOKEN value in .env file with provided token and timestamp
        of token expiration.

    :param token: Bearer Token obtained from API authorization call
    :type token: AnyStr
    :param expires_in: Number (in seconds) when token will expire
    :type expires_in: int
    """
    try:
        dotenv_path = os.path.join(ROOT_DIR, ".env")
        expiration_time = datetime.utcnow() + timedelta(seconds=expires_in)

        # Small buffer to account for time sync issues
        buffer = 5 * 60
        expiration_timestamp = (expiration_time - timedelta(seconds=buffer)).timestamp()

        set_key(dotenv_path=dotenv_path, key_to_set="TOKEN", value_to_set=token)
        set_key(
            dotenv_path=dotenv_path,
            key_to_set="TOKEN_EXPIRATION",
            value_to_set=str(expiration_timestamp),
        )

        logthis.info("Bearer token and expiration updated in .env file")
    except OSError as e:
        logthis.error(f"Failed to update the .env file due to a file error: {e}")
    except Exception as e:
        logthis.error(f"An unexpected error occurred while update the .env file: {e}")


# Check token expiration
def token_valid() -> bool:
    """Ensures Bearer token present in .env is valid (not expired)"""
    token_expiration = os.getenv("TOKEN_EXPIRATION")
    if token_expiration:
        expiration_time = datetime.fromtimestamp(
            float(token_expiration), tz=timezone.utc
        )
        current_time = datetime.utcnow().replace(tzinfo=timezone.utc)
        return current_time < expiration_time
    return False


# Retrieve Bearer Token
async def fetch_token() -> Optional[AnyStr]:
    """
    Fetches a new Bearer Token using client credentials. Updates .env
        if successful.

    :return: The new Bearer Token (str), or None if the fetch fails.
    """
    async with aiohttp.ClientSession() as session:
        payload = {
            "client_id": jamf_client_id,
            "grant_type": "client_credentials",
            "client_secret": jamf_client_secret,
        }
        token_headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = await session.post(
                url=f"{jamf_url}/api/oauth/token", data=payload, headers=token_headers
            )
            response.raise_for_status()

            json_response = await response.json()
            token = json_response.get("access_token", "")
            expires = int(json_response.get("expires_in", ""))

            update_env(token=token, expires_in=expires)
            logthis.info(f"Token obtained successfully. Expires in {expires} seconds")
            return token
        except aiohttp.ClientResponseError as e:
            logthis.warn(f"Failed to fetch bearer token. Status code: {e.status}")
        except Exception as e:
            logthis.error(f"Unexpected error during token fetch: {e}")

    return None


# Async API call
async def fetch_json(url: AnyStr, session: aiohttp.ClientSession):
    """
    Asynchronously fetches JSON data from a specified URL using a session.

    :param url: URL to fetch the JSON data from.
    :type url: AnyStr
    :param session: Async session used to make the request, instance of aiohttp.ClientSession.
    :type session: aiohttp.ClientSession
    :return: JSON data as a dictionary or an empty dictionary on error.
    """
    try:
        async with session.get(url, headers=headers) as response:
            return await response.json()
    except Exception as e:
        logthis.error(f"Error fetching JSON: {e}")
        return {}


# Use Jamf API to retrieve all Patch titles IDs
async def get_policies() -> List:
    """
    Asynchronously retrieves all patch software titles' IDs using the Jamf API.

    :return: List of software title IDs or an empty list on error.
    :rtype: List
    """
    try:
        # Ensure bearer token is valid
        if not token_valid():
            logthis.info("Bearer token is not valid, refreshing token.")
            new_token = await fetch_token()
            if not new_token:
                logthis.error("Failed to refresh token, aborting...")
                return []

        async with aiohttp.ClientSession() as session:
            url = f"{jamf_url}/api/v2/patch-software-title-configurations"
            response = await fetch_json(url=url, session=session)

            # Verify response is list type as expected
            if not isinstance(response, list):
                logthis.error("Unexpected response format: expected a list.")
                return []

            # Check if all elements in the list are dictionaries
            if not all(isinstance(item, dict) for item in response):
                logthis.error("Unexpected response format: all items should be dictionaries.")
                return []

            logthis.info("Patch policies obtained as expected.")
            return [title["id"] for title in response]

    except Exception as e:
        logthis.error(f"Error retrieving policies from API: {e}")
        return []


# Use Jamf API to retrieve active patch summaries based upon supplied ID
async def get_summaries(policy_ids: List) -> List:
    """
    Retrieves active patch summaries for given policy IDs using the Jamf API.

    :param policy_ids: List of policy IDs to retrieve summaries for.
    :type policy_ids: List
    :return: List of dictionaries containing patch summaries or an empty list on error.
    :rtype: List
    """
    try:
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

    except Exception as e:
        logthis.error(f"Error retrieving summaries: {e}")
        return []


# Create excel spreadsheet with patch data for export
def export_to_excel(patch_reports: List[Dict], output_dir: AnyStr) -> AnyStr:
    """
    Exports patch data to an Excel spreadsheet in the specified output directory.

    :param patch_reports: List of dictionaries containing patch report data.
    :type patch_reports: List[Dict]
    :param output_dir: Directory to save the Excel spreadsheet.
    :type output_dir: AnyStr
    :return: Path to the created Excel spreadsheet or error message.
    :rtype: AnyStr
    """
    try:
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

    except Exception as e:
        logthis.info(f"Error occurred trying to export to Excel: {e}")
        return "Error exporting to Excel. Check log files in data directory."


# Create PDF from Excel file
def export_excel_to_pdf(excel_file: AnyStr, date_format: AnyStr = "%B %d %Y") -> None:
    """
    Creates a PDF report from an Excel file containing patch data.

    :param excel_file: Path to the Excel file to convert to PDF.
    :type excel_file: AnyStr
    :param date_format: The date format string for the PDF report header.
    :type date_format: AnyStr
    """
    try:
        # Read excel file
        df = pd.read_excel(excel_file)

        # Create instance of FPDF
        pdf = PDF(date_format=date_format)
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

    except Exception as e:
        logthis.error(f"Error occurred trying to export PDF: {e}")
