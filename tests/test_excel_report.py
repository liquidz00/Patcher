import os
import pandas as pd
from unittest.mock import patch
from src.patcher.model.excel_report import ExcelReport


def test_export_to_excel_success(sample_patch_reports, temp_output_dir):
    excel_report = ExcelReport()

    excel_path = excel_report.export_to_excel(sample_patch_reports, temp_output_dir)

    assert excel_path is not None
    assert os.path.exists(excel_path)
    df = pd.read_excel(excel_path)
    assert not df.empty
    assert list(df.columns) == [
        "Software Title",
        "Patch Released",
        "Hosts Patched",
        "Missing Patch",
        "Completion Percent",
        "Total Hosts",
    ]


def test_export_to_excel_dataframe_creation_error(temp_output_dir):
    excel_report = ExcelReport()

    with patch.object(pd, "DataFrame", side_effect=ValueError("Test Error")):
        excel_path = excel_report.export_to_excel([], temp_output_dir)

        assert excel_path is None
