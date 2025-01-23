import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

import asyncclick as click

from ..models.patch import PatchTitle
from ..utils.animation import Animation
from ..utils.data_manager import DataManager
from ..utils.exceptions import APIResponseError, PatcherError
from ..utils.logger import LogMe
from ..utils.pdf_report import PDFReport
from .api_client import ApiClient


class ReportManager:
    def __init__(
        self,
        api_client: ApiClient,
        data_manager: DataManager,
        pdf_report: PDFReport,
        debug=False,
    ):
        """
        Handles the generation and management of patch reports.

        :param api_client: Interacts with the Jamf API to retrieve data needed for reporting.
        :type api_client: :class:`~patcher.client.api_client.ApiClient`
        :param data_manager: Generates Excel reports from collected patch data.
        :type data_manager: :class:`~patcher.utils.data_manager.DataManager`
        :param pdf_report: Generates PDF reports from the Excel files, adding visual elements..
        :type pdf_report: :class:`~patcher.utils.pdf_report.PDFReport`
        :param debug: Overrides animation of `~patcher.client.report_manager.ReportManager.process_reports` method if True.
        :type debug: :py:class:`bool`
        """
        self.api_client = api_client
        self.data_manager = data_manager
        self.pdf_report = pdf_report
        self.debug = debug
        self.log = LogMe(self.__class__.__name__)

    def calculate_ios_on_latest(
        self,
        device_versions: List[Dict[str, str]],
        latest_versions: List[Dict[str, str]],
    ) -> List[PatchTitle]:
        """
        Analyzes iOS version data to determine how many enrolled devices are on the latest version.

        This method compares the operating system versions of managed devices with the latest versions
        provided by the SOFA feed, calculating how many devices are fully updated.

        :param device_versions: A list of dictionaries containing devices and their respective iOS versions.
        :type device_versions: :py:obj:`~typing.List` [:py:obj:`~typing.Dict`]
        :param latest_versions: A list of the most recent iOS versions available.
        :type latest_versions: :py:obj:`~typing.List` [:py:obj:`~typing.Dict`]
        :return: A list of ``PatchTitle`` objects, each representing a summary of the patch status for an iOS version.
        :rtype: :py:obj:`~typing.List` [:class:`~patcher.models.patch.PatchTitle`]
        :raises PatcherError: If a KeyError or ZeroDivisionError is encountered.
        """
        self.log.debug("Attempting to calculate iOS devices on latest version.")

        try:
            latest_versions_dict = {lv.get("OSVersion"): lv for lv in latest_versions}
            version_counts = {
                version: {"count": 0, "total": 0} for version in latest_versions_dict.keys()
            }
            for device in device_versions:
                device_os = device.get("OS")
                if not device_os:
                    self.log.warning(f"Device missing OS information: {device}")

                major_version = device_os.split(".")[0]
                if major_version in version_counts:
                    version_counts[major_version]["total"] += 1
                    if device_os == latest_versions_dict[major_version]["ProductVersion"]:
                        version_counts[major_version]["count"] += 1

            mapped = [
                PatchTitle(
                    title=f"iOS {latest_versions_dict[version]['ProductVersion']}",
                    released=latest_versions_dict[version]["ReleaseDate"],
                    hosts_patched=counts["count"],
                    missing_patch=counts["total"] - counts["count"],
                    latest_version=latest_versions_dict[version]["ProductVersion"],
                    completion_percent=round((counts["count"] / counts["total"]) * 100, 2),
                    total_hosts=counts["total"],
                )
                for version, counts in version_counts.items()
                if counts["total"] > 0
            ]
            self.log.info(f"iOS version analysis completed with {len(mapped)} summaries generated.")
            return mapped
        except KeyError as e:
            raise PatcherError(
                "Encountered KeyError while calculating iOS devices on latest version.",
                error_msg=str(e),
            )
        except ZeroDivisionError as e:
            raise PatcherError(
                "Division by zero encountered during iOS Device percentage calculation.",
                error_msg=str(e),
            )

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

        This function is not intended to be called directly by users, but rather is a key part of the CLI's
        automated reporting process. It handles all the necessary steps from data collection to file generation,
        ensuring that reports are accurate, complete, and formatted according to the user's preferences.

        :param path: The directory where the reports will be saved. It must be a valid directory, not a file.
        :type path: :py:obj:`~typing.Union` [:py:class:`str` | :py:class:`~pathlib.Path`]

        :param pdf: If True, generates PDF versions of the reports in addition to Excel.
        :type pdf: :py:class:`bool`

        :param sort: Specifies the column by which to sort the reports (e.g., 'released' or 'completion_percent').
        :type sort: :py:obj:`~typing.Optional` [:py:class:`str`]

        :param omit: If True, omits patches that were released within the last 48 hours.
        :type omit: :py:class:`bool`

        :param ios: If True, includes iOS device data in the reports.
        :type ios: :py:class:`bool`

        :param date_format: Specifies the date format for headers in the reports. Default is "%B %d %Y" (Month Day Year).
        :type date_format: :py:class:`str`
        """
        animation = Animation(enable_animation=not self.debug)

        async with animation.error_handling():
            self.log.debug("Starting report generation process.")
            output_path = self._validate_directory(path)

            self.log.debug("Attempting to retrieve policy IDs.")
            try:
                patch_ids = await self.api_client.get_policies()
                self.log.info(f"Retrieved policy IDs for {len(patch_ids)} policies.")
            except APIResponseError as e:
                self.log.error(f"Unable to obtain policy IDs from Jamf instance. Details: {e}")
                raise PatcherError(
                    "Failed to retrieve policy IDs from Jamf instance.", error_msg=str(e)
                )

            self.log.debug("Attempting to retrieve patch summaries.")
            try:
                patch_reports = await self.api_client.get_summaries(patch_ids)
                self.log.info(f"Received policy summaries for {len(patch_reports)} policies.")
            except APIResponseError as e:
                self.log.error(f"Unable to fetch patch summaries from Jamf instance. Details: {e}")
                raise PatcherError(
                    "Failed to retrieve patch summaries from Jamf instance.", error_msg=str(e)
                )

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
        self._success(len(patch_reports), output_path)

    def _validate_directory(self, path: Union[str, Path]) -> str:
        """Validates or creates the reports directory."""
        self.log.debug(f"Validating directory: {path}")
        output_path = os.path.expanduser(path)

        try:
            os.makedirs(output_path, exist_ok=True)
            reports_dir = os.path.join(output_path, "Patch-Reports")
            os.makedirs(reports_dir, exist_ok=True)
            self.log.info(f"Reports directory '{reports_dir}' validated successfully.")
            return reports_dir
        except (OSError, PermissionError) as e:
            self.log.error(f"Failed to create Patch Reports directory. Details: {e}")
            raise PatcherError(
                "Failed to create Patch Reports directory path.",
                path=output_path,
                error_msg=str(e),
            )

    async def _sort(self, patch_reports: List[PatchTitle], sort_key: str) -> List[PatchTitle]:
        """Sorts provided patch reports by sort key."""
        self.log.debug(f"Detected sorting option '{sort_key}'")
        sort_key = sort_key.lower().replace(" ", "_")

        try:
            sorted_reports = await asyncio.to_thread(
                lambda: sorted(patch_reports, key=lambda x: getattr(x, sort_key))
            )
            self.log.info(f"Patch reports sorted successfully by '{sort_key}'.")
            return sorted_reports
        except (KeyError, AttributeError) as e:
            self.log.error(
                f"Invalid column name for sorting: {sort_key.title().replace('_', ' ')}. Details: {e}"
            )
            raise PatcherError(
                "Unable to sort patch reports due to invalid column name.",
                column=str(sort_key.title().replace("_", " ")),
                error_msg=str(e),
            )

    async def _omit(self, patch_reports: List[PatchTitle]) -> List[PatchTitle]:
        """Omits patch policies with patches released in past 48 hours from exported reports."""
        cutoff = datetime.now() - timedelta(hours=48)
        self.log.debug(
            f"Detected omit flag. Attempting to omit reports with patches released since {cutoff}."
        )
        original_count = len(patch_reports)
        patch_reports = await asyncio.to_thread(
            lambda: [
                report
                for report in patch_reports
                if datetime.strptime(report.released, "%b %d %Y") < cutoff
            ]
        )
        omitted_count = original_count - len(patch_reports)
        self.log.info(f"Omitted {omitted_count} policies with recent patches.")
        return patch_reports

    async def _ios(self, patch_reports: List[PatchTitle]) -> List[PatchTitle]:
        """Adds iOS information to exported reports."""
        self.log.debug("Attempting to fetch iOS device IDs.")
        try:
            device_ids = await self.api_client.get_device_ids()
            self.log.info(f"Received {len(device_ids)} device IDs successfully.")
        except APIResponseError as e:
            self.log.error(f"Unable to obtain iOS Device IDs from Jamf instance. Details: {e}")
            raise PatcherError(
                "Unable to obtain iOS Device IDs from Jamf instance.", error_msg=str(e)
            )

        self.log.debug("Attempting to fetch iOS version data for enrolled devices.")
        try:
            device_versions = await self.api_client.get_device_os_versions(device_ids=device_ids)
            self.log.info(f"Successfully obtained OS versions for {len(device_versions)} devices.")
        except APIResponseError as e:
            self.log.error(
                f"Received empty response obtaining device OS versions from Jamf instance. Details: {e}"
            )
            raise PatcherError(
                "Failed retrieving iOS Device versions from Jamf instance.",
                ids=device_ids,
                error_msg=str(e),
            )

        self.log.debug("Attempting to retrieve SOFA feed.")
        try:
            latest_versions = await self.api_client.get_sofa_feed()
            self.log.info("Obtained latest version information from SOFA feed successfully.")
        except APIResponseError as e:
            self.log.error(f"Failed to fetch data from SOFA feed. Details: {e}")
            raise PatcherError("Error fetching data from SOFA feed.", error_msg=str(e))

        try:
            ios_data = self.calculate_ios_on_latest(
                device_versions=device_versions, latest_versions=latest_versions
            )
        except PatcherError as e:
            self.log.error(
                f"Encountered error trying to calculate amount of iOS devices on latest version. Details: {e}"
            )
            raise

        patch_reports.extend(ios_data)
        self.log.info("iOS information successfully appended to patch reports.")
        return patch_reports

    async def _generate_excel(self, patch_reports: List[PatchTitle], reports_dir: str) -> str:
        """Generates Excel spreadsheet from passed patch reports to passed reports directory."""
        self.log.debug(f"Attempting Excel export to {reports_dir}")
        try:
            excel_file = await asyncio.to_thread(
                self.data_manager.export_to_excel, patch_reports, reports_dir
            )
            self.log.info(f"Excel report saved to {excel_file}.")
            return excel_file
        except PatcherError as e:
            self.log.error(f"Error exporting Excel document to {reports_dir}. Details: {e}")
            raise PatcherError(
                "Failed exporting data to Excel.",
                report_dir=reports_dir,
                error_msg=str(e),
            )

    async def _generate_pdf(self, excel_file: str, date_format: str) -> None:
        """Generates PDF report from passed excel file with custom date format."""
        self.log.debug(f"Attempting to generate PDF report from {excel_file}.")
        try:
            pdf_report = PDFReport()
            await asyncio.to_thread(pdf_report.export_excel_to_pdf, excel_file, date_format)
            self.log.info("PDF file generated successfully.")
        except PatcherError as e:
            self.log.error(f"Error generating PDF file. Details: {e}")
            raise PatcherError(
                "Failed generating PDF file.",
                excel_file=excel_file,
                error_msg=str(e),
            )

    def _success(self, report_count: int, reports_dir: str) -> None:
        self.log.info(f"{report_count} patch reports saved successfully to {reports_dir}.")
        click.echo(
            click.style(f"\r✅ Success! Reports saved to {reports_dir}", bold=True, fg="green")
        )
