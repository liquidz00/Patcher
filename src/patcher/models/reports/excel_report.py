import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd

from ...utils import logger
from ..patch import PatchTitle

logthis = logger.setup_child_logger("ExcelReport", __name__)


class ExcelReport:
    """
    Handles the generation of Excel reports from patch data.

    The ``ExcelReport`` class provides functionality to export patch data into an
    Excel spreadsheet, saving it to the specified directory.
    """

    @staticmethod
    def export_to_excel(
        patch_reports: List[PatchTitle], output_dir: Union[str, Path]
    ) -> Optional[str]:
        """
        Exports patch data to an Excel spreadsheet in the specified output directory.

        This method converts a list of :class:`~patcher.models.patch.PatchTitle` instances into a DataFrame and
        writes it to an Excel file. The file is saved with a timestamp in the filename.

        :param patch_reports: List of ``PatchTitle`` instances containing patch report data.
        :type patch_reports: List[PatchTitle]
        :param output_dir: Directory where the Excel spreadsheet will be saved.
        :type output_dir: Union[str, Path]
        :return: Path to the created Excel spreadsheet, or ``None`` if an error occurs.
        :rtype: Optional[str]
        """
        if isinstance(output_dir, Path):
            output_dir = str(output_dir)

        current_date = datetime.now().strftime("%m-%d-%y")

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
