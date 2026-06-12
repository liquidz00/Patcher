"""Tests for :mod:`patcher.core.serialization` — the Excel → ``PatchTitle`` adapter."""

from __future__ import annotations

import pandas as pd
import pytest
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.serialization import excel_to_titles


def _write_export_xlsx(path, rows):
    """Write an .xlsx in the Title-Cased shape Exporter.export produces (title_id dropped)."""
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


class TestExcelToTitles:
    def test_roundtrips_exported_report(self, tmp_path):
        path = _write_export_xlsx(
            tmp_path / "patch-report.xlsx",
            [
                {
                    "Title": "Firefox",
                    "Released": "Jun 09 2026",
                    "Hosts Patched": 8,
                    "Missing Patch": 2,
                    "Latest Version": "151.0",
                    "Completion Percent": 80.0,
                    "Total Hosts": 10,
                },
                {
                    "Title": "Slack",
                    "Released": "May 01 2026",
                    "Hosts Patched": 5,
                    "Missing Patch": 5,
                    "Latest Version": "4.40",
                    "Completion Percent": 50.0,
                    "Total Hosts": 10,
                },
            ],
        )

        titles = excel_to_titles(path)

        assert [t.title for t in titles] == ["Firefox", "Slack"]
        firefox = titles[0]
        assert firefox.hosts_patched == 8
        assert firefox.missing_patch == 2
        # Recomputed by the model validator from hosts/missing, not read from the file.
        assert firefox.total_hosts == 10
        assert firefox.completion_percent == 80.0
        # title_id is dropped on export; a placeholder is synthesized so hydration succeeds.
        assert firefox.title_id == "0"

    def test_raises_on_malformed_excel(self, tmp_path):
        path = tmp_path / "not-a-report.xlsx"
        pd.DataFrame([{"Foo": 1, "Bar": 2}]).to_excel(path, index=False)
        with pytest.raises(PatcherError, match="Could not read any patch titles"):
            excel_to_titles(path)

    def test_raises_on_empty_excel(self, tmp_path):
        path = tmp_path / "empty.xlsx"
        pd.DataFrame([]).to_excel(path, index=False)
        with pytest.raises(PatcherError):
            excel_to_titles(path)
