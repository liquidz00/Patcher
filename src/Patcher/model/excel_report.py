import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, AnyStr, Optional
from src.Patcher.client.config_manager import ConfigManager
from src.Patcher import logger

logthis = logger.setup_child_logger("excel_report", __name__)


class ExcelReport:
    """Handles the generation of Excel reports from patch data."""

    def __init__(self, config: ConfigManager):
        """
        Initializes the ExcelReport with the provided ConfigManager.

        :param config: Instance of ConfigManager for managing configuration.
        :type config: ConfigManager
        """
        self.config = config

    @staticmethod
    def export_to_excel(
        patch_reports: List[Dict], output_dir: AnyStr
    ) -> Optional[AnyStr]:
        """
        Exports patch data to an Excel spreadsheet in the specified output directory.

        :param patch_reports: List of dictionaries containing patch report data.
        :type patch_reports: List[Dict]
        :param output_dir: Directory to save the Excel spreadsheet.
        :type output_dir: AnyStr
        :return: Path to the created Excel spreadsheet or None on error.
        :rtype: Optional[AnyStr]
        """
        current_date = datetime.now().strftime("%m-%d-%y")

        column_order = [
            "software_title",
            "patch_released",
            "hosts_patched",
            "missing_patch",
            "completion_percent",
            "total_hosts",
        ]

        try:
            df = pd.DataFrame(patch_reports, columns=column_order)
            df.columns = [column.replace("_", " ").title() for column in column_order]
        except ValueError as e:
            logthis.error(f"Error creating DataFrame: {e}")
            return None
        except Exception as e:
            logthis.error(
                f"Unhandled exception occurred trying to export to Excel: {e}"
            )
            return None

        excel_path = os.path.join(output_dir, f"patch-report-{current_date}.xlsx")
        df.to_excel(excel_path, index=False)
        logthis.info(f"Excel spreadsheet created successfully at {excel_path}")
        return excel_path
