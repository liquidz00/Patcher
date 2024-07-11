import os
from datetime import datetime
from typing import AnyStr, List, Optional

import pandas as pd

from ... import logger
from ..patch import PatchTitle

logthis = logger.setup_child_logger("ExcelReport", __name__)


class ExcelReport:
    """Handles the generation of Excel reports from patch data."""

    @staticmethod
    def export_to_excel(patch_reports: List[PatchTitle], output_dir: AnyStr) -> Optional[AnyStr]:
        """
        Exports patch data to an Excel spreadsheet in the specified output directory.

        :param patch_reports: List of PatchTitle instances containing patch report data.
        :type patch_reports: List[PatchTitle]
        :param output_dir: Directory to save the Excel spreadsheet.
        :type output_dir: AnyStr
        :return: Path to the created Excel spreadsheet or None on error.
        :rtype: Optional[AnyStr]
        """
        current_date = datetime.now().strftime("%m-%d-%y")

        # column_order = [
        #     "software_title",
        #     "patch_released",
        #     "hosts_patched",
        #     "missing_patch",
        #     "completion_percent",
        #     "total_hosts",
        # ]

        try:
            df = pd.DataFrame([patch.model_dump() for patch in patch_reports])
            df.columns = [column.replace("_", " ").title() for column in df.columns]
        except ValueError as e:
            logthis.error(f"Error creating DataFrame: {e}")
            return None
        except Exception as e:
            logthis.error(f"Unhandled exception occurred trying to export to Excel: {e}")
            return None

        excel_path = os.path.join(output_dir, f"patch-report-{current_date}.xlsx")
        df.to_excel(excel_path, index=False)
        logthis.info(f"Excel spreadsheet created successfully at {excel_path}")
        return excel_path
