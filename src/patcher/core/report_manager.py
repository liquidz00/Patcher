import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

from ..client.api_client import ApiClient
from .data_manager import DataManager
from .exceptions import APIResponseError, PatcherError
from .installomator import Installomator
from .logger import LogMe
from .models.patch import PatchTitle


class ReportManager:
    def __init__(
        self,
        api_client: ApiClient,
        data_manager: DataManager,
        debug: bool = False,
        installomator: Installomator | None = None,
    ):
        """
        Handles the generation and management of patch reports.

        :param api_client: Interacts with the Jamf API to retrieve data needed for reporting.
        :type api_client: :class:`~patcher.client.api_client.ApiClient`
        :param data_manager: Generates Excel reports from collected patch data.
        :type data_manager: :class:`~patcher.core.data_manager.DataManager`
        :param debug: Overrides animation of `~patcher.core.report_manager.ReportManager.process_reports` method if True.
        :type debug: bool
        :param installomator: An optional :class:`~patcher.core.installomator.Installomator` object for matching. Defaults to creating a new object during init.
        :type installomator: :class:`~patcher.core.installomator.Installomator`
        """
        self.api_client = api_client
        self.data_manager = data_manager
        self.debug = debug
        self.log = LogMe(self.__class__.__name__)
        self.iom = installomator or Installomator()

    def _validate_directory(self, path: str | Path) -> str:
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

    async def _sort(self, patch_reports: list[PatchTitle], sort_key: str) -> list[PatchTitle]:
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

    async def _omit(self, patch_reports: list[PatchTitle]) -> list[PatchTitle]:
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

    async def _ios(self, patch_reports: list[PatchTitle]) -> list[PatchTitle]:
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

    def calculate_ios_on_latest(
        self,
        device_versions: list[dict[str, str]],
        latest_versions: list[dict[str, str]],
    ) -> list[PatchTitle]:
        """
        Analyzes iOS version data to determine how many enrolled devices are on the latest version.

        This method compares the operating system versions of managed devices with the latest versions
        provided by the SOFA feed, calculating how many devices are fully updated.

        :param device_versions: A list of dictionaries containing devices and their respective iOS versions.
        :type device_versions: list[dict[str, str]]
        :param latest_versions: A list of the most recent iOS versions available.
        :type latest_versions: list[dict[str, str]]
        :return: A list of ``PatchTitle`` objects, each representing a summary of the patch status for an iOS version.
        :rtype: list[:class:`~patcher.core.models.patch.PatchTitle`]
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
                    title_id="iOS",
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
