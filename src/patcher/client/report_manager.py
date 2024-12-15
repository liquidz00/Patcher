import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

import asyncclick as click

from ..models.patch import PatchTitle
from ..models.reports.excel_report import ExcelReport
from ..models.reports.pdf_report import PDFReport
from ..utils import exceptions, logger
from ..utils.animation import Animation
from ..utils.decorators import check_token
from .api_client import ApiClient
from .config_manager import ConfigManager
from .token_manager import TokenManager
from .ui_manager import UIConfigManager


class ReportManager:
    """
    Handles the generation and management of patch reports within the patcher CLI tool.

    This class coordinates various components such as configuration, token management, API interaction,
    and report generation (both Excel and PDF) to produce comprehensive reports on patch statuses.
    """

    def __init__(
        self,
        config: ConfigManager,
        token_manager: TokenManager,
        api_client: ApiClient,
        excel_report: ExcelReport,
        pdf_report: PDFReport,
        ui_config: UIConfigManager,
        debug=False,
    ):
        """
        Initializes the patcher class with the provided components.

        :param config: Manages the configuration settings, including credentials.
        :type config: :class:`~patcher.client.config_manager.ConfigManager`

        :param token_manager: Handles the authentication tokens required for API access..
        :type token_manager: :class:`~patcher.client.token_manager.TokenManager`

        :param api_client: Interacts with the Jamf API to retrieve data needed for reporting.
        :type api_client: :class:`~patcher.client.api_client.ApiClient`

        :param excel_report: Generates Excel reports from collected patch data.
        :type excel_report: :class:`~patcher.models.reports.excel_report.ExcelReport`

        :param pdf_report: Generates PDF reports from the Excel files, adding visual elements..
        :type pdf_report: :class:`~patcher.models.reports.pdf_report.PDFReport`

        :param ui_config: Manages the UI configuration for PDF report generation.
        :type ui_config: :class:`~patcher.client.ui_manager.UIConfigManager`

        :param debug: Enables debug mode if True, providing detailed logging.
        :type debug: bool
        """
        self.config = config
        self.token_manager = token_manager
        self.api_client = api_client
        self.excel_report = excel_report
        self.pdf_report = pdf_report
        self.ui_config = ui_config
        self.debug = debug
        self.log = logger.LogMe(self.__class__.__name__, debug=self.debug)

    def calculate_ios_on_latest(
        self,
        device_versions: List[Dict[str, str]],
        latest_versions: List[Dict[str, str]],
    ) -> Optional[List[PatchTitle]]:
        """
        Analyzes the iOS version data to determine how many enrolled devices are on the latest version.

        This method compares the operating system versions of managed devices with the latest versions
        provided by the SOFA feed, calculating how many devices are fully updated.

        :param device_versions: A list of dictionaries containing devices and their respective iOS versions.
        :type device_versions: List[Dict[str, str]]
        :param latest_versions: A list of the most recent iOS versions available.
        :type latest_versions: List[Dict[str, str]]
        :return: A list of ``PatchTitle`` objects, each representing a summary of the patch status for an iOS version.
        :rtype: Optional[List[PatchTitle]]

        This method does not interact directly with the user but is crucial in the internal process
        of generating accurate reports that reflect the patch status across iOS devices.
        """
        if not device_versions or not latest_versions:
            self.log.error("Error calculating iOS Versions. Received None instead of a List")
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
                    PatchTitle(
                        title=f"iOS {latest_versions_dict[version]['ProductVersion']}",
                        released=latest_versions_dict[version]["ReleaseDate"],
                        hosts_patched=counts["count"],
                        missing_patch=counts["total"] - counts["count"],
                        latest_version=latest_versions_dict[version]["ProductVersion"],
                        completion_percent=completion_percent,
                        total_hosts=counts["total"],
                    )
                )

        return mapped

    @check_token
    async def process_reports(
        self,
        path: Union[str, Path],
        pdf: bool,
        sort: Optional[str],
        omit: bool,
        ios: bool,
        date_format: str = "%B %d %Y",
    ) -> None:
        """
        Asynchronously generates and saves patch reports, with options for customization.

        This method is the core of the report generation process, orchestrating the collection
        of patch data, sorting, filtering, and ultimately saving the data to an Excel file.
        It can also generate a PDF report and include additional iOS device data.

        :param path: The directory where the reports will be saved. It must be a valid directory, not a file.
        :type path: Union[str, Path]

        :param pdf: If True, generates PDF versions of the reports in addition to Excel.
        :type pdf: bool

        :param sort: Specifies the column by which to sort the reports (e.g., 'released' or 'completion_percent').
        :type sort: Optional[str]

        :param omit: If True, omits patches that were released within the last 48 hours.
        :type omit: bool

        :param ios: If True, includes iOS device data in the reports.
        :type ios: bool

        :param date_format: Specifies the date format for headers in the reports. Default is "%B %d %Y" (Month Day Year).
        :type date_format: str

        :return: None
        :rtype: None

        :raises exceptions.DirectoryCreationError: If the provided path is a file or directories cannot be created.
        :raises exceptions.PolicyFetchError: If no policy IDs are retrieved.
        :raises exceptions.SummaryFetchError: If no patch summaries are retrieved.
        :raises exceptions.SortError: If sorting by an invalid column name.
        :raises exceptions.DeviceIDFetchError: If mobile device IDs cannot be retrieved.
        :raises exceptions.DeviceOSFetchError: If device OS versions cannot be retrieved.
        :raises exceptions.SofaFeedError: If there is an issue with retrieving data from the SOFA feed.
        :raises exceptions.ExportError: If there is an error exporting reports to Excel or PDF.

        This function is not intended to be called directly by users, but rather is a key part of the CLI's
        automated reporting process. It handles all the necessary steps from data collection to file generation,
        ensuring that reports are accurate, complete, and formatted according to the user's preferences.
        """
        animation = Animation(enable_animation=not self.debug)

        async with animation.error_handling(self.log):
            self.log.debug("Beginning patcher process...")
            output_path = self._validate_directory(path)

            # Async operations for patch data
            self.log.debug("Attempting to retrieve policy IDs.")
            patch_ids = await self.api_client.get_policies()

            if not patch_ids:
                self.log.error(
                    "Policy ID API call returned an empty list. Aborting...",
                )
                raise exceptions.PolicyFetchError()
            self.log.debug(f"Retrieved policy IDs for {len(patch_ids)} policies.")

            self.log.debug("Attempting to retrieve patch summaries.")
            patch_reports = await self.api_client.get_summaries(patch_ids)

            if not patch_reports:
                self.log.error("Error establishing patch summaries.")
                raise exceptions.SummaryFetchError()
            else:
                self.log.debug(f"Received policy summaries for {len(patch_reports)} policies.")

            # (option) Sort
            if sort:
                patch_reports = await self._sort(patch_reports, sort)

            # (option) Omit
            if omit:
                patch_reports = await self._omit(patch_reports)

            # (option) iOS
            if ios:
                patch_reports = await self._ios(patch_reports)

            # Generate reports
            excel_file = await self._generate_excel(
                patch_reports=patch_reports, reports_dir=output_path
            )

            if pdf:
                await self._generate_pdf(excel_file=excel_file, date_format=date_format)

            # Manually stop animation to show success message cleanly
            animation.stop_event.set()
            self.log.debug("Patcher finished as expected!")
            self._success(len(patch_reports), output_path)

    def _validate_directory(self, path: Union[str, Path]) -> str:
        output_path = os.path.expanduser(path)
        if os.path.exists(output_path) and os.path.isfile(output_path):
            self.log.error(
                f"Provided path {output_path} is a file, not a directory. Aborting...",
            )
            raise exceptions.DirectoryCreationError(path=output_path)

        # Ensure directories exist
        try:
            os.makedirs(output_path, exist_ok=True)
            reports_dir = os.path.join(output_path, "Patch-Reports")
            os.makedirs(reports_dir, exist_ok=True)
            self.log.debug(f"Reports directory created at '{reports_dir}'.")
            return reports_dir
        except OSError as e:
            self.log.error(f"Failed to create directory: {e}")
            raise exceptions.DirectoryCreationError(f"Failed to create directory: {e}")

    async def _sort(self, patch_reports: List[PatchTitle], sort_key: str) -> List[PatchTitle]:
        self.log.debug(f"Detected sorting option '{sort_key}'")
        sort_key = sort_key.lower().replace(" ", "_")

        try:
            sorted_reports = await asyncio.to_thread(
                lambda: sorted(patch_reports, key=lambda x: getattr(x, sort_key))
            )
            self.log.debug(f"Patch reports sorted by '{sort_key}'.")
            return sorted_reports
        except (KeyError, AttributeError):
            self.log.error(
                f"Invalid column name for sorting: {sort_key.title().replace('_', ' ')}. Aborting...",
            )
            raise exceptions.SortError(column=str(sort_key.title().replace("_", " ")))

    async def _omit(self, patch_reports: List[PatchTitle]) -> List[PatchTitle]:
        self.log.debug(
            "Detected omit flag. Omitting policies with patches released in past 48 hours."
        )
        cutoff = datetime.now() - timedelta(hours=48)
        original_count = len(patch_reports)
        patch_reports = await asyncio.to_thread(
            lambda: [
                report
                for report in patch_reports
                if datetime.strptime(report.released, "%b %d %Y") < cutoff
            ]
        )
        omitted_count = original_count - len(patch_reports)
        self.log.debug(f"Omitted {omitted_count} policies with recent patches.")
        return patch_reports

    async def _ios(self, patch_reports: List[PatchTitle]) -> List[PatchTitle]:
        self.log.debug("Detected ios flag. Including iOS information in reports.")
        self.log.debug("Attempting to fetch mobile device IDs.")
        device_ids = await self.api_client.get_device_ids()
        if not device_ids:
            self.log.error(
                "Received ClientError response when obtaining mobile device IDs",
            )
            raise exceptions.DeviceIDFetchError(
                reason="Received ClientError response when obtaining mobile device IDs"
            )

        self.log.debug(f"Obtained device IDs for {len(device_ids)} devices.")
        device_versions = await self.api_client.get_device_os_versions(device_ids=device_ids)
        latest_versions = await self.api_client.get_sofa_feed()
        if not device_versions:
            self.log.error(
                "Received empty response obtaining device OS versions from Jamf. Exiting...",
            )
            raise exceptions.DeviceOSFetchError(
                reason="Received empty response obtaining device OS versions from Jamf."
            )
        elif not latest_versions:
            self.log.error("Received empty response from SOFA feed. Exiting...")
            raise exceptions.SofaFeedError(
                reason="Received empty response from SOFA feed. Unable to verify amount of devices on latest version."
            )

        self.log.debug("Calculating devices on latest version.")
        ios_data = self.calculate_ios_on_latest(
            device_versions=device_versions, latest_versions=latest_versions
        )
        patch_reports.extend(ios_data)
        self.log.debug("iOS information successfully appended to patch reports.")
        return patch_reports

    async def _generate_excel(self, patch_reports: List[PatchTitle], reports_dir: str) -> str:
        self.log.debug("Generating excel file...")
        try:
            excel_file = await asyncio.to_thread(
                self.excel_report.export_to_excel, patch_reports, reports_dir
            )
            self.log.debug(f"Excel file generated successfully at '{excel_file}'.")
            return excel_file
        except ValueError as e:
            self.log.error(f"Error exporting to excel: {e}")
            raise exceptions.ExportError(f"Error exporting to excel: {e}")

    async def _generate_pdf(self, excel_file: str, date_format: str) -> None:
        self.log.debug("Generating PDF file...")
        try:
            pdf_report = PDFReport(self.ui_config)
            await asyncio.to_thread(pdf_report.export_excel_to_pdf, excel_file, date_format)
            self.log.debug("PDF file generated successfully.")
        except (OSError, PermissionError) as e:
            self.log.error(f"Error generating PDF file. Check file permissions: {e}")
            raise exceptions.ExportError(file_path=excel_file)
        except Exception as e:
            self.log.error(f"Unhandled error encountered: {e}")
            raise exceptions.ExportError(f"Unhandled error encountered: {e}")

    def _success(self, report_count: int, reports_dir: str) -> None:
        self.log.debug(f"{report_count} patch reports saved successfully to {reports_dir}.")
        success_msg = click.style(
            f"\rSuccess! Reports saved to {reports_dir}", bold=True, fg="green"
        )
        click.echo(success_msg)
