import os
from datetime import datetime
from pathlib import Path
from typing import List, Union

import pandas as pd

from ...utils.exceptions import PatcherError
from ...utils.logger import LogMe
from ..patch import PatchTitle


class ExcelReport:
    def __init__(self):
        """
        The ``ExcelReport`` class provides functionality to export patch data into an
        Excel spreadsheet, saving it to the specified directory.
        """
        self.log = LogMe(self.__class__.__name__)

    def export_to_excel(self, patch_reports: List[PatchTitle], output_dir: Union[str, Path]) -> str:
        """
        This method converts a list of :class:`~patcher.models.patch.PatchTitle` instances into a DataFrame and
        writes it to an Excel file. The file is saved with a timestamp in the filename.

        :param patch_reports: List of ``PatchTitle`` instances containing patch report data.
        :type patch_reports: :py:obj:`~typing.List` of :class:`~patcher.models.patch.PatchTitle`
        :param output_dir: Directory where the Excel spreadsheet will be saved.
        :type output_dir: :py:obj:`~typing.Union` of :py:class:`str` or :py:class:`~pathlib.Path`
        :return: Path to the created Excel spreadsheet.
        :rtype: :py:class:`str`
        :raises PatcherError: If the dataframe is unable to be created or the excel file unable to be saved.
        """
        self.log.debug(f"Attempting Excel export to {str(output_dir)}")
        if isinstance(output_dir, Path):
            output_dir = str(output_dir)

        current_date = datetime.now().strftime("%m-%d-%y")
        excluded_columns = ["install_label"]

        try:
            df = pd.DataFrame([patch.model_dump() for patch in patch_reports])
            df = df.drop(columns=excluded_columns, errors="ignore")  # Drop excluded columns
            df.columns = [column.replace("_", " ").title() for column in df.columns]
        except (ValueError, pd.errors.EmptyDataError) as e:
            self.log.error(f"Error creating DataFrame. Details: {e}")
            raise PatcherError(
                "Encountered error creating DataFrame.", file_path=str(output_dir), error_msg=str(e)
            )

        try:
            excel_path = os.path.join(output_dir, f"patch-report-{current_date}.xlsx")
            df.to_excel(excel_path, index=False)
            self.log.info(f"Excel spreadsheet created successfully at {excel_path}")
            return excel_path
        except (OSError, PermissionError) as e:
            self.log.error(f"Unable to save DataFrame to {str(output_dir)}: {e}")
            raise PatcherError(
                "Encountered error saving DataFrame.",
                file_path=str(output_dir),
                error_msg=str(e),
            )
