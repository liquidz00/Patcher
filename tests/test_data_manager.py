import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from src.patcher.core.data_manager import DataManager
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.models.patch import PatchTitle


class TestBuildAndCache:
    def test_build_and_cache_returns_frame_and_writes_parquet(self, sample_patch_reports, tmp_path):
        """build_and_cache serializes titles to a DataFrame and snapshots it to the cache."""
        dm = DataManager()
        dm.cache_dir = tmp_path

        df = dm.build_and_cache(sample_patch_reports)

        assert list(df["Title"]) == ["Example Software"]
        parquet_files = list(tmp_path.glob("*.parquet"))
        assert len(parquet_files) == 1
        assert_frame_equal(DataManager.load(parquet_files[0]), df)

    def test_build_and_cache_skips_write_when_disabled(self, sample_patch_reports, tmp_path):
        """With caching disabled the frame is still built, but nothing is written to disk."""
        dm = DataManager(disable_cache=True)
        dm.cache_dir = tmp_path

        df = dm.build_and_cache(sample_patch_reports)

        assert not df.empty
        assert list(tmp_path.glob("*.parquet")) == []

    def test_create_dataframe_value_error_raises_patchererror(self, sample_patch_reports):
        dm = DataManager(disable_cache=True)
        with patch.object(pd, "DataFrame", side_effect=ValueError("Test Error")):
            with pytest.raises(PatcherError, match="Encountered error creating DataFrame."):
                dm.build_and_cache(sample_patch_reports)

    def test_create_dataframe_empty_data_error_raises_patchererror(self, sample_patch_reports):
        dm = DataManager(disable_cache=True)
        with patch.object(pd, "DataFrame", side_effect=pd.errors.EmptyDataError):
            with pytest.raises(PatcherError, match="Encountered error creating DataFrame"):
                dm.build_and_cache(sample_patch_reports)


class TestCache:
    def test_cache_property(self):
        data_manager = DataManager()
        assert data_manager.cache_off is False

    def test_cache_property_false(self):
        data_manager = DataManager(disable_cache=True)
        assert data_manager.cache_off is True

    def test_clean_cache_removes_expired_files(self, temp_output_path):
        """Ensure clean_cache removes only expired files."""
        data_manager = DataManager()
        data_manager.cache_dir = temp_output_path

        expired_file = temp_output_path / "expired.pkl"
        valid_file = temp_output_path / "valid.pkl"

        expired_file.touch()
        valid_file.touch()

        expired_time = (datetime.now() - timedelta(days=91)).timestamp()
        valid_time = (datetime.now() - timedelta(days=15)).timestamp()
        os.utime(expired_file, (expired_time, expired_time))
        os.utime(valid_file, (valid_time, valid_time))

        mock_iterdir = MagicMock(return_value=[expired_file, valid_file])

        with patch.object(Path, "iterdir", mock_iterdir):
            data_manager._clean_cache()

        # Ensure only the expired file is removed
        assert not expired_file.exists()
        assert valid_file.exists()

    def test_clean_cache_no_permissions(self):
        """Ensure clean_cache handles missing permissions gracefully."""
        # Mock the cache directory and files
        with (
            patch("pathlib.Path.iterdir") as mock_iterdir,
            patch("pathlib.Path.unlink", side_effect=PermissionError("Test Permission Error")),
        ):
            # Simulate a file in the cache directory
            cache_file = MagicMock()
            cache_file.suffix = ".pkl"
            cache_file.stat.return_value.st_mtime = (
                datetime.now() - timedelta(days=91)
            ).timestamp()
            mock_iterdir.return_value = [cache_file]

            # Initialize DataManager and run the method
            data_manager = DataManager(disable_cache=True)
            data_manager._clean_cache()

            # Ensure the file was attempted to be deleted, but an error was logged
            cache_file.unlink.assert_called_once()

    def test_clean_cache_continues_after_failed_delete(self):
        """A locked file logs a warning but pruning continues to the next file."""
        expired = (datetime.now() - timedelta(days=91)).timestamp()

        def _expired_file(unlink_error=None):
            f = MagicMock()
            f.suffix = ".parquet"
            f.is_file.return_value = True
            f.stat.return_value.st_mtime = expired
            if unlink_error:
                f.unlink.side_effect = unlink_error
            return f

        bad = _expired_file(PermissionError("locked"))
        good = _expired_file()

        data_manager = DataManager(disable_cache=True)
        with patch.object(Path, "iterdir", return_value=[bad, good]):
            data_manager._clean_cache()

        bad.unlink.assert_called_once()
        good.unlink.assert_called_once()  # would never run if the loop aborted on `bad`

    def test_get_latest_dataset_no_files(self):
        """Ensure get_latest_dataset returns None when no datasets are available."""
        data_manager = DataManager(disable_cache=True)
        with patch.object(data_manager, "get_cached_files", return_value=[]):
            assert data_manager.get_latest_dataset() is None

    def test_cache_data_writes_parquet_and_load_round_trips(self, tmp_path):
        """New caches are written as Parquet (version-stable) and load() reads them back."""
        dm = DataManager()
        dm.cache_dir = tmp_path
        df = pd.DataFrame([{"title": "Firefox", "completion_percent": 80.0, "total_hosts": 10}])

        dm._cache_data(df)

        parquet_files = list(tmp_path.glob("*.parquet"))
        assert len(parquet_files) == 1  # Parquet, not pickle
        assert_frame_equal(DataManager.load(parquet_files[0]), df)

    def test_load_wraps_unreadable_pickle_with_recovery_hint(self, tmp_path):
        """A legacy .pkl that can't be unpickled surfaces an actionable PatcherError."""
        bad = tmp_path / "patch_data_bad.pkl"
        bad.write_bytes(b"not a valid pickle stream")
        with pytest.raises(PatcherError, match="different version of pandas") as excinfo:
            DataManager.load(bad)
        assert "reset cache" in excinfo.value.recovery  # presentation-only attr, not in str()

    def test_select_baseline_picks_by_window(self, tmp_path):
        """select_baseline: all_time → earliest, since → earliest-in-window, else → default."""
        cached = []
        for i, days_ago in enumerate((30, 10, 1)):  # oldest → newest
            p = tmp_path / f"snap{i}.parquet"
            p.write_bytes(b"")
            ts = (datetime.now() - timedelta(days=days_ago)).timestamp()
            os.utime(p, (ts, ts))
            cached.append(p)

        assert DataManager.select_baseline(cached, all_time=True, default=cached[-1]) == cached[0]
        # 20-day window includes only the 10-day and 1-day snapshots → earliest of those
        assert (
            DataManager.select_baseline(cached, since=timedelta(days=20), default=cached[-1])
            == cached[1]
        )
        assert DataManager.select_baseline(cached, default=cached[-2]) == cached[-2]
        with pytest.raises(PatcherError, match="requested window"):
            DataManager.select_baseline(cached, since=timedelta(hours=1), default=cached[-1])


class TestTitlesProperty:
    def test_titles_property_uninitialized(self):
        """Test titles property access when uninitialized."""
        data_manager = DataManager()
        with patch.object(data_manager, "get_latest_dataset", return_value=None):
            with pytest.raises(
                PatcherError, match="No dataset available, unable to proceed with validation."
            ):
                _ = data_manager.titles

    def test_titles_property_setter_invalid_type(self):
        """Test titles setter with invalid type."""
        data_manager = DataManager()
        with pytest.raises(
            PatcherError, match="Value Invalid Type must be an list of PatchTitle objects."
        ):
            data_manager.titles = "Invalid Type"

    def test_titles_property_setter_empty_list(self):
        """Test titles setter with an empty list."""
        data_manager = DataManager()
        with pytest.raises(PatcherError, match="PatchTitles cannot be set to an empty list"):
            data_manager.titles = []

    def test_titles_property_setter_valid(self):
        """Test titles setter with valid PatchTitle objects."""
        data_manager = DataManager()
        patch_titles = [
            PatchTitle(
                title="Patch A",
                title_id="0",
                released="2022-01-01",
                hosts_patched=50,
                missing_patch=10,
                latest_version="1.0.0",
            ),
            PatchTitle(
                title="Patch B",
                title_id="1",
                released="2023-01-01",
                hosts_patched=30,
                missing_patch=20,
                latest_version="2.0.0",
            ),
        ]
        data_manager.titles = patch_titles
        assert data_manager.titles == patch_titles
