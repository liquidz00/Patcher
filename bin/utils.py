import os
import pandas as pd
import aiohttp
import asyncio
import subprocess
import json

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

# Load .env
load_dotenv(dotenv_path=globals.ENV_PATH)

# Set environment variables
jamf_url = globals.JAMF_URL
jamf_client_id = globals.JAMF_CLIENT_ID
jamf_client_secret = globals.JAMF_CLIENT_SECRET
jamf_token = globals.JAMF_TOKEN

# Headers for API calls
headers = globals.HEADERS

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
def convert_timezone(utc_time_str: AnyStr) -> Optional[AnyStr]:
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
        logthis.error(f"Invalid time format provided. Details: {e}")
        return None


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
    expiration_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Small buffer to account for time sync issues
    buffer = 5 * 60
    expiration_timestamp = (expiration_time - timedelta(seconds=buffer)).timestamp()

    try:
        set_key(dotenv_path=globals.ENV_PATH, key_to_set="TOKEN", value_to_set=token)
        set_key(
            dotenv_path=globals.ENV_PATH,
            key_to_set="TOKEN_EXPIRATION",
            value_to_set=str(expiration_timestamp),
        )
        logthis.info("Bearer token and expiration updated in .env file")
    except (OSError, ValueError) as e:
        logthis.error(f"Failed to update the .env file due to a file error: {e}")


# Check token expiration
def token_valid() -> bool:
    """Ensures Bearer token present in .env is valid (not expired)"""
    token_expiration = os.getenv("TOKEN_EXPIRATION")
    if token_expiration:
        expiration_time = datetime.fromtimestamp(
            float(token_expiration), tz=timezone.utc
        )
        current_time = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
        return current_time < expiration_time
    return False


# Retrieve Bearer Token
async def fetch_token() -> Optional[AnyStr]:
    """
    Fetches a new Bearer Token using either client credentials.
    Updates .env if successful.

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
        except aiohttp.ClientResponseError as e:
            logthis.warn(f"Failed to fetch bearer token. Status code: {e.status}")
            return None

        json_response = await response.json()
        token = json_response.get("access_token", "")
        expires = int(json_response.get("expires_in", 0))
        if not token or not expires:
            return None
        update_env(token=token, expires_in=expires)
        logthis.info(f"Token obtained successfully. Expires in {expires} seconds")
        return token


# Async API call
async def fetch_json(url: AnyStr, session: aiohttp.ClientSession) -> Dict:
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
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientResponseError as e:
        logthis.error(f"Received a client error while fetching JSON from {url}: {e}")
    except Exception as e:
        logthis.error(f"Error fetching JSON: {e}")
    return {}


# Token lifetime check
async def check_token_lifetime(client_id: AnyStr = globals.JAMF_CLIENT_ID) -> bool:
    """
    Ensures the bearer token lifetime is valid (longer than 1 minute, ideally above 10 minutes)

    :param client_id: The client ID property to match, defaults to client_id property in .env
    :return: True if token lifetime is greater than 5 minutes
    """
    async with aiohttp.ClientSession() as session:
        url = f"{jamf_url}/api/v1/api-integrations"
        response = await fetch_json(url=url, session=session)
        if not response:
            logthis.error("Received empty dictionary fetching response.")
            return False
        results = response.get("results")
        if not results:
            logthis.error("Invalid response received from API call.")
            return False

        lifetime = None
        for result in results:
            if result.get("clientId") == client_id:
                # accessTokenLifetimeSeconds value is extracted once match found
                lifetime = result.get("accessTokenLifetimeSeconds")
                break

        if lifetime is None:
            # Client ID not found
            logthis.error(f"No matching Client ID found for {client_id}.")
            return False

        if lifetime <= 0:
            logthis.error("Token lifetime is invalid.")
            return False

        # Calculate duration in different units
        minutes = lifetime / 60
        hours = minutes / 60
        days = hours / 24
        months = days / 30

        # Throw error if duration of lifetime is less than 1 minute
        if minutes < 1:
            logthis.error("Token life time is less than 1 minute.")
            return False
        elif 5 <= minutes <= 10:
            # Throws warning if token lifetime is between 5-10 minutes
            logthis.warning("Token lifetime is between 5-10 minutes.")
        else:
            # Lifetime duration logged otherwise
            logthis.info(
                f"Token lifetime: {minutes:.2f} minutes, {hours:.2f} hours, {days:.2f} days, {months:.2f} months."
            )
        return True


# Use Jamf API to retrieve all Patch titles IDs
async def get_policies() -> Optional[List]:
    """
    Asynchronously retrieves all patch software titles' IDs using the Jamf API.

    :return: List of software title IDs or an empty list on error.
    :rtype: List
    """
    async with aiohttp.ClientSession() as session:
        url = f"{jamf_url}/api/v2/patch-software-title-configurations"
        response = await fetch_json(url=url, session=session)

        # Verify response is list type as expected
        if not isinstance(response, list):
            logthis.error("Unexpected response format: expected a list.")
            return None

        # Check if all elements in the list are dictionaries
        if not all(isinstance(item, dict) for item in response):
            logthis.error(
                "Unexpected response format: all items should be dictionaries."
            )
            return None

        logthis.info("Patch policies obtained as expected.")
        return [title.get("id") for title in response]


# Use Jamf API to retrieve active patch summaries based upon supplied ID
async def get_summaries(policy_ids: List) -> Optional[List]:
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
    except aiohttp.ClientError as e:
        logthis.error(f"Received ClientError trying to retreive patch summaries: {e}")
        return None

    policy_summaries = [
        {
            "software_title": summary.get("title"),
            "patch_released": convert_timezone(summary.get("releaseDate")),
            "hosts_patched": summary.get("upToDate"),
            "missing_patch": summary.get("outOfDate"),
            "completion_percent": (
                round(
                    (
                        summary.get("upToDate")
                        / (summary.get("upToDate") + summary.get("outOfDate"))
                    )
                    * 100,
                    2,
                )
                if summary.get("upToDate") + summary.get("outOfDate") > 0
                else 0
            ),
            "total_hosts": summary.get("upToDate") + summary.get("outOfDate"),
        }
        for summary in summaries
        if summary
    ]
    logthis.info(
        f"Successfully obtained policy summaries for {len(policy_summaries)} policies."
    )
    return policy_summaries


# iOS Functionality - Get mobile device IDs from Jamf Pro API
async def get_device_ids() -> Optional[List[int]]:
    """
    Asynchronously fetches the list of mobile device IDs from the Jamf Pro API.

    :return: A list of mobile device IDs.
    """
    url = f"{jamf_url}/api/v2/mobile-devices"

    try:
        async with aiohttp.ClientSession() as session:
            response = await fetch_json(url=url, session=session)
    except aiohttp.ClientError as e:
        logthis.error(f"Error fetching device IDs: {e}")
        return None
    devices = response.get("results", [])

    if not devices:
        logthis.error("Received invalid data set during device ID API call.")
        return None

    device_ids = [device.get("id") for device in devices if device]
    logthis.info(f"Received {len(devices)} device IDs successfully.")
    return device_ids


# iOS Functionality - Get OS Version and Type from Jamf Pro API
async def get_device_os_versions(
    device_ids: List[int],
) -> Optional[List[Dict[AnyStr, AnyStr]]]:
    """
    Asynchronously fetches the OS version and serial number for each device ID from the Jamf Pro API.

    :param device_ids: A list of mobile device IDs.
    :type device_ids: List[int]
    :return: A list of dictionaries containing the serial number and OS version.
    """
    try:
        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_json(
                    url=f"{jamf_url}/api/v2/mobile-devices/{device}/detail",
                    session=session,
                )
                for device in device_ids
            ]
            subsets = await asyncio.gather(*tasks)
    except aiohttp.ClientError as e:
        logthis.error(f"Received ClientError fetching device OS information: {e}")
        return None

    if not subsets:
        logthis.error("Received empty response obtaining device OS information.")
        return None

    devices = [
        {
            "SN": subset.get("serialNumber"),
            "OS": subset.get("osVersion"),
        }
        for subset in subsets
    ]
    logthis.info(f"Successfully obtained OS versions for {len(devices)} devices.")
    return devices


# iOS Functionality - Get iOS machine readable feeds from SOFA (sofa.macadmins.io)
def get_sofa_feed() -> Optional[List[Dict[AnyStr, AnyStr]]]:
    """
    Fetches iOS Data feeds from SOFA and extracts latest OS version information

    :return: A list of dictionaries containing Base OS Version, latest iOS Version and release date.
    """

    # Utilize curl to avoid SSL Verification errors for end-users on managed devices
    command = "curl -s 'https://sofa.macadmins.io/v1/ios_data_feed.json'"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        logthis.error(f"Encountered error executing subprocess command: {e}")
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logthis.error(f"Error decoding JSON data: {e}")
        return None

    os_versions = data.get("OSVersions", [])
    latest_versions = []
    for version in os_versions:
        version_info = version.get("Latest", {})
        latest_versions.append(
            {
                "OSVersion": version.get("OSVersion"),
                "ProductVersion": version_info.get("ProductVersion"),
                "ReleaseDate": convert_timezone(version_info.get("ReleaseDate")),
            }
        )
    return latest_versions


# iOS Functionality - Calculate amount of devices on latest version
def calculate_ios_on_latest(
    device_versions: List[Dict[AnyStr, AnyStr]],
    latest_versions: List[Dict[AnyStr, AnyStr]],
) -> Optional[List[Dict]]:
    """
    Calculates the amount of enrolled devices are on the latest version of their respective operating system.

    :param device_versions: A list of nested dictionaries containing devices and corresponding operating system versions
    :type device_versions: List[Dict[AnyStr, AnyStr]]
    :param latest_versions: A list of latest available iOS versions, from SOFA feed
    :type latest_versions: List[Dict[AnyStr, AnyStr]]
    :return: A list with calculated data per iOS version
    """
    if not device_versions or not latest_versions:
        logthis.error("Error calculating iOS Versions. Received None instead of a List")
        return None

    latest_versions_dict = {lv.get("OSVersion"): lv for lv in latest_versions}

    version_counts = {
        version: {"count": 0, "total": 0} for version in latest_versions_dict.keys()
    }

    for device in device_versions:
        device_os = device.get("OS")
        major_version = device_os.split(".")[0]
        if major_version in version_counts:
            version_counts[major_version]["total"] += 1
            if device_os == latest_versions_dict[major_version]["ProductVersion"]:
                version_counts[major_version]["count"] += 1

    mapped = []
    for version, counts in version_counts.items():
        if counts["total"] > 0:
            completion_percent = round((counts["count"] / counts["total"]) * 100, 2)
            mapped.append(
                {
                    "software_title": f"iOS {latest_versions_dict[version]['ProductVersion']}",
                    "patch_released": latest_versions_dict[version]["ReleaseDate"],
                    "hosts_patched": counts["count"],
                    "missing_patch": counts["total"] - counts["count"],
                    "completion_percent": completion_percent,
                    "total_hosts": counts["total"],
                }
            )

    return mapped


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
        logthis.info(f"Excel spreadsheet created successfully at {excel_path}")
        return excel_path

    except Exception as e:
        logthis.error(f"Error occurred trying to export to Excel: {e}")
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
