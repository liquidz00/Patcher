"""Unit coverage for ``patcher.cli._helpers`` orchestration functions."""

import warnings
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.patcher.cli import _helpers
from src.patcher.core.exceptions import APIResponseError, PatcherError


class TestWarningFormat:
    def test_terse_one_line(self):
        assert (
            _helpers.warning_format("oops", DeprecationWarning, "f.py", 1)
            == "DeprecationWarning: oops\n"
        )


class TestParseSince:
    @pytest.mark.parametrize(
        "value,expected",
        [("30d", timedelta(days=30)), ("24h", timedelta(hours=24)), ("1w", timedelta(weeks=1))],
    )
    def test_valid(self, value, expected):
        assert _helpers.parse_since(value) == expected

    @pytest.mark.parametrize("bad", ["30x", "abc", "", "d30"])
    def test_invalid_raises(self, bad):
        with pytest.raises(PatcherError, match="--since"):
            _helpers.parse_since(bad)


class TestParseIsoDate:
    def test_valid(self):
        assert _helpers.parse_iso_date("2026-05-17") == date(2026, 5, 17)

    def test_invalid_raises(self):
        with pytest.raises(PatcherError, match="ISO"):
            _helpers.parse_iso_date("05/17/2026")


class TestInitializeCache:
    def test_creates_when_parent_exists(self, tmp_path):
        (tmp_path / "Caches").mkdir()
        cache = tmp_path / "Caches" / "Patcher"
        _helpers.initialize_cache(cache)
        assert cache.exists()

    def test_skips_when_parent_missing(self, tmp_path):
        cache = tmp_path / "nope" / "Patcher"  # parent doesn't exist
        _helpers.initialize_cache(cache)
        assert not cache.exists()  # skipped, no error

    def test_swallows_oserror(self, tmp_path, mocker):
        cache = tmp_path / "Patcher"  # parent (tmp_path) exists
        mocker.patch.object(Path, "mkdir", side_effect=OSError("nope"))
        _helpers.initialize_cache(cache)  # must not raise


class TestGetDataManager:
    def test_creates_once_and_reuses(self, mocker):
        mock_dm_cls = mocker.patch("src.patcher.cli._helpers.DataManager")
        ctx = MagicMock()
        ctx.obj = {"disable_cache": False}
        first = _helpers.get_data_manager(ctx)
        second = _helpers.get_data_manager(ctx)
        assert first is second
        mock_dm_cls.assert_called_once_with(disable_cache=False)


class TestInstallProcessHooks:
    def test_installs_excepthook_and_warning_filter(self, mocker):
        mock_excepthook = mocker.patch("src.patcher.cli._helpers.install_terminal_excepthook")
        mock_simplefilter = mocker.patch.object(warnings, "simplefilter")
        original_fmt = warnings.formatwarning
        try:
            _helpers._install_cli_process_hooks()
            mock_excepthook.assert_called_once()
            mock_simplefilter.assert_called_once()
            assert warnings.formatwarning is _helpers.warning_format
        finally:
            warnings.formatwarning = original_fmt


class TestValidateOutputDir:
    def test_creates_reports_subdir(self, tmp_path):
        result = _helpers._validate_output_dir(str(tmp_path))
        assert result.endswith("Patch-Reports")
        assert Path(result).exists()

    def test_raises_on_oserror(self, mocker):
        mocker.patch("os.makedirs", side_effect=OSError("read-only"))
        with pytest.raises(PatcherError, match="Patch Reports"):
            _helpers._validate_output_dir("/some/path")


# Test successful report processing
class TestReportProcessor:
    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::src.patcher.core.exceptions.InstallomatorWarning")
    async def test_process_reports_success(
        self, stop_event_fixture, patcher_instance, mock_policy_response, mock_summary_response
    ):
        with patch.object(patcher_instance, "export") as mock_export_to_excel:
            await _helpers.process_reports(
                patcher_instance,
                path="~/",
                formats={"excel", "html"},
                sort=None,
                omit=False,
                ios=False,
                report_title="Test Report",
                header_color="",
            )

            assert mock_export_to_excel.called

    # Test process reports with invalid path
    @pytest.mark.asyncio
    @patch("os.makedirs", side_effect=OSError("Read-only file system"))
    @patch("os.path.isfile")
    async def test_process_reports_invalid_path(
        self,
        mock_isfile,
        mock_makedirs,
        stop_event_fixture,
        patcher_instance,
        mock_policy_response,
        mock_summary_response,
    ):
        mock_isfile.return_value = True
        with pytest.raises(PatcherError):
            await _helpers.process_reports(
                patcher_instance,
                path="/invalid/path",
                formats={"excel", "html"},
                sort=None,
                omit=False,
                ios=False,
                report_title="Test Report",
                header_color="",
            )

    # Test invalid sort
    @pytest.mark.asyncio
    async def test_invalid_sort(
        self,
        stop_event_fixture,
        patcher_instance,
    ):
        with pytest.raises(PatcherError):
            with patch.object(patcher_instance, "export") as mock_error:
                await _helpers.process_reports(
                    patcher_instance,
                    path="~/",
                    formats={"excel", "html"},
                    sort="sort_column",
                    omit=False,
                    ios=False,
                    report_title="Test Report",
                    header_color="",
                )

                mock_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_reports_all_optional_steps(self, patcher_instance, mocker):
        """sort + omit + ios + device-details + matching all run through to export."""
        mocker.patch(
            "src.patcher.cli._helpers.sort_titles",
            new_callable=AsyncMock,
            side_effect=lambda r, s: r,
        )
        mocker.patch(
            "src.patcher.cli._helpers.omit_recent", new_callable=AsyncMock, side_effect=lambda r: r
        )
        mocker.patch(
            "src.patcher.cli._helpers.append_ios_status",
            new_callable=AsyncMock,
            side_effect=lambda r, j: r,
        )
        mocker.patch("src.patcher.cli._helpers.match_titles", new_callable=AsyncMock)
        patcher_instance.jamf.get_title_reports = AsyncMock(return_value={"1": []})

        await _helpers.process_reports(
            patcher_instance,
            path="~/",
            formats={"excel"},
            sort="released",
            omit=True,
            ios=True,
            report_title="T",
            header_color="",
            device_details=True,
        )

        assert patcher_instance.export.called
        patcher_instance.jamf.get_title_reports.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_reports_policy_fetch_error(self, patcher_instance):
        patcher_instance.jamf.get_policies = AsyncMock(
            side_effect=APIResponseError("down", status_code=503)
        )
        with pytest.raises(PatcherError, match="policy IDs"):
            await _helpers.process_reports(
                patcher_instance,
                path="~/",
                formats={"excel"},
                sort=None,
                omit=False,
                ios=False,
                report_title="T",
                header_color="",
            )

    @pytest.mark.asyncio
    async def test_process_reports_summary_fetch_error(self, patcher_instance):
        patcher_instance.jamf.get_summaries = AsyncMock(
            side_effect=APIResponseError("down", status_code=503)
        )
        with pytest.raises(PatcherError, match="patch summaries"):
            await _helpers.process_reports(
                patcher_instance,
                path="~/",
                formats={"excel"},
                sort=None,
                omit=False,
                ios=False,
                report_title="T",
                header_color="",
            )

    @pytest.mark.asyncio
    async def test_process_reports_matching_error_reraises(self, patcher_instance, mocker):
        mocker.patch(
            "src.patcher.cli._helpers.match_titles",
            new_callable=AsyncMock,
            side_effect=APIResponseError("boom", status_code=500),
        )
        with pytest.raises(APIResponseError):
            await _helpers.process_reports(
                patcher_instance,
                path="~/",
                formats={"excel"},
                sort=None,
                omit=False,
                ios=False,
                report_title="T",
                header_color="",
            )

    @pytest.mark.asyncio
    async def test_process_reports_matching_404_is_swallowed(self, patcher_instance, mocker):
        mocker.patch(
            "src.patcher.cli._helpers.match_titles",
            new_callable=AsyncMock,
            side_effect=APIResponseError("not found", status_code=404, not_found=True),
        )
        await _helpers.process_reports(
            patcher_instance,
            path="~/",
            formats={"excel"},
            sort=None,
            omit=False,
            ios=False,
            report_title="T",
            header_color="",
        )
        assert patcher_instance.export.called  # 404 swallowed, run continues
