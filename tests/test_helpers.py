"""Unit coverage for ``patcher.cli._helpers`` orchestration functions."""

import warnings
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.patcher.cli import _helpers
from src.patcher.core.exceptions import PatcherError


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
