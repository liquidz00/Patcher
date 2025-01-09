import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from src.patcher.models.patch import PatchTitle
from src.patcher.utils.data_manager import DataManager
from src.patcher.utils.exceptions import FetchError, PatcherError


def test_export_to_excel_success(sample_patch_reports, temp_output_dir):
    data_manager = DataManager()
    excel_path = data_manager.export_to_excel(sample_patch_reports, temp_output_dir)

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
        "Install Label",
    ]


def test_export_to_excel_dataframe_creation_error(temp_output_dir):
    data_manager = DataManager(disable_cache=True)
    with patch.object(pd, "DataFrame", side_effect=ValueError("Test Error")):
        with pytest.raises(PatcherError, match="Encountered error creating DataFrame."):
            data_manager.export_to_excel([], temp_output_dir)


def test_cache_property():
    data_manager = DataManager()
    assert data_manager.cache_off is False


def test_cache_property_false():
    data_manager = DataManager(disable_cache=True)
    assert data_manager.cache_off is True


def test_titles_property_uninitialized():
    """Test titles property access when uninitialized."""
    data_manager = DataManager()
    with patch.object(data_manager, "get_latest_dataset", return_value=None):
        with pytest.raises(
            PatcherError, match="No dataset available, unable to proceed with validation."
        ):
            _ = data_manager.titles


def test_titles_property_setter_invalid_type():
    """Test titles setter with invalid type."""
    data_manager = DataManager()
    with pytest.raises(
        PatcherError, match="Value Invalid Type must be an list of PatchTitle objects."
    ):
        data_manager.titles = "Invalid Type"


def test_titles_property_setter_empty_list():
    """Test titles setter with an empty list."""
    data_manager = DataManager()
    with pytest.raises(FetchError, match="PatchTitles cannot be set to an empty list"):
        data_manager.titles = []


def test_titles_property_setter_valid():
    """Test titles setter with valid PatchTitle objects."""
    data_manager = DataManager()
    patch_titles = [
        PatchTitle(
            title="Patch A",
            released="2022-01-01",
            hosts_patched=50,
            missing_patch=10,
            latest_version="1.0.0",
        ),
        PatchTitle(
            title="Patch B",
            released="2023-01-01",
            hosts_patched=30,
            missing_patch=20,
            latest_version="2.0.0",
        ),
    ]
    data_manager.titles = patch_titles
    assert data_manager.titles == patch_titles


# Edge case tests
def test_export_to_excel_empty_patch_reports(temp_output_dir):
    """Ensure export_to_excel handles empty patch_reports gracefully."""
    data_manager = DataManager()
    with patch.object(pd, "DataFrame", side_effect=pd.errors.EmptyDataError):
        with pytest.raises(PatcherError, match="Encountered error creating DataFrame."):
            data_manager.export_to_excel([], temp_output_dir)


def test_export_to_excel_invalid_directory():
    """Ensure export_to_excel raises an error for invalid output directory."""
    data_manager = DataManager()
    invalid_dir = "/invalid/path/to/output"
    with pytest.raises(PatcherError, match="Encountered error saving DataFrame"):
        data_manager.export_to_excel([], invalid_dir)


def test_export_to_excel_permission_error(temp_output_path):
    """Simulate a permission error when writing to an output directory."""
    data_manager = DataManager()
    temp_file = temp_output_path / "patch-report.xlsx"

    mock_patches = [
        PatchTitle(
            title="Patch A",
            released="2022-01-01",
            hosts_patched=50,
            missing_patch=10,
            latest_version="1.0.0",
            completion_percent=(50 / (50 + 10)) * 100,
            total_hosts=50 + 10,
        ),
        PatchTitle(
            title="Patch B",
            released="2023-01-01",
            hosts_patched=30,
            missing_patch=20,
            latest_version="2.0.0",
            completion_percent=(30 / (30 + 20)) * 100,
            total_hosts=30 + 20,
        ),
        PatchTitle(
            title="Patch C",
            released="2023-12-01",
            hosts_patched=20,
            missing_patch=5,
            latest_version="3.0.0",
            completion_percent=(20 / (20 + 5)) * 100,
            total_hosts=20 + 5,
        ),
    ]
    with patch("os.makedirs", side_effect=PermissionError("Test Permission Error")):
        with pytest.raises(PatcherError, match="Encountered error saving DataFrame"):
            data_manager.export_to_excel(mock_patches, temp_file)


def test_clean_cache_removes_expired_files():
    """Ensure clean_cache removes only expired files."""
    # Mock the cache directory and files
    with (
        patch("pathlib.Path.iterdir") as mock_iterdir,
        patch("pathlib.Path.unlink") as mock_unlink,
        patch("datetime.datetime") as mock_datetime,
    ):

        # Simulate the current time
        current_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = current_time

        # Simulate files in the cache directory
        expired_file = MagicMock()
        expired_file.suffix = ".pkl"
        expired_file.stat.return_value.st_mtime = (current_time - timedelta(days=31)).timestamp()

        valid_file = MagicMock()
        valid_file.suffix = ".pkl"
        valid_file.stat.return_value.st_mtime = (current_time - timedelta(days=15)).timestamp()

        mock_iterdir.return_value = [expired_file, valid_file]

        # Initialize DataManager and run the method
        data_manager = DataManager()
        data_manager._clean_cache()

        # Ensure only the expired file is deleted
        expired_file.unlink.assert_called_once()
        valid_file.unlink.assert_not_called()


def test_clean_cache_no_permissions():
    """Ensure clean_cache handles missing permissions gracefully."""
    # Mock the cache directory and files
    with (
        patch("pathlib.Path.iterdir") as mock_iterdir,
        patch("pathlib.Path.unlink", side_effect=PermissionError("Test Permission Error")),
    ):

        # Simulate a file in the cache directory
        cache_file = MagicMock()
        cache_file.suffix = ".pkl"
        cache_file.stat.return_value.st_mtime = (datetime.now() - timedelta(days=31)).timestamp()
        mock_iterdir.return_value = [cache_file]

        # Initialize DataManager and run the method
        data_manager = DataManager(disable_cache=True)
        data_manager._clean_cache()

        # Ensure the file was attempted to be deleted, but an error was logged
        cache_file.unlink.assert_called_once()


def test_get_latest_dataset_no_files():
    """Ensure get_latest_dataset returns None when no datasets are available."""
    data_manager = DataManager(disable_cache=True)
    with patch("pathlib.Path.glob", return_value=[]):
        assert data_manager.get_latest_dataset() is None


def test_load_cached_data_with_corrupted_files(mock_data_manager):
    """Ensure load_cached_data skips corrupted files."""
    corrupted_file = MagicMock(spec=Path)
    corrupted_file.name = "corrupted_cache.pkl"
    corrupted_file.__str__.return_value = "/mocked/path/corrupted_cache.pkl"

    mock_data_manager.get_cached_files.return_value = [corrupted_file]

    with patch("pickle.load", side_effect=pickle.UnpicklingError("Test Unpickling error")):
        loaded_data = mock_data_manager.load_cached_data()

    # Assert that no valid data was loaded
    assert len(loaded_data) == 0
