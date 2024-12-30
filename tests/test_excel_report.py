import os
from unittest.mock import patch

import pandas as pd
import pytest
from src.patcher.models.reports.excel_report import ExcelReport
from src.patcher.utils.exceptions import ExportError


def test_export_to_excel_success(sample_patch_reports, temp_output_dir):
    excel_report = ExcelReport()

    excel_path = excel_report.export_to_excel(sample_patch_reports, temp_output_dir)

    assert excel_path is not None
    assert os.path.exists(excel_path)
    df = pd.read_excel(excel_path)
    assert not df.empty
    assert list(df.columns) == [
        "Title",
        "Released",
        "Hosts Patched",
        "Missing Patch",
        "Latest Version",
        "Completion Percent",
        "Total Hosts",
    ]


def test_export_to_excel_dataframe_creation_error(temp_output_dir):
    excel_report = ExcelReport()

    with patch.object(pd, "DataFrame", side_effect=ValueError("Test Error")):
        with pytest.raises(ExportError) as excinfo:
            excel_report.export_to_excel([], temp_output_dir)

        assert "Error exporting data - file_path: Error creating DataFrame: Test Error" in str(
            excinfo.value
        )
