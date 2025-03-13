import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from src.patcher.models.patch import PatchTitle
from src.patcher.utils.data_manager import DataManager
from src.patcher.utils.exceptions import PatcherError


@pytest.fixture
def mock_formats():
    return {"excel"}


@pytest.mark.asyncio
async def test_export_to_excel_success(sample_patch_reports, temp_output_dir, mock_formats):
    data_manager = DataManager()

    with patch.object(data_manager, "_cache_data", return_value=None) as mock_cache_data:
        exported_files = await data_manager.export(
            sample_patch_reports, temp_output_dir, "Test Report", formats=mock_formats
        )

        excel_path = exported_files.get("excel")  # type: ignore
        assert excel_path is not None
        assert os.path.exists(excel_path)

        df = pd.read_excel(excel_path)
        assert not df.empty
        assert list(df.columns) == [
            "Title",
            # "Title Id",
            "Released",
            "Hosts Patched",
            "Missing Patch",
            "Latest Version",
            "Completion Percent",
            "Total Hosts",
            # "Install Label",
        ]

        args, _ = mock_cache_data.call_args
        cached_df = args[0]

        # Account for cached dataframe having all columns
        common_columns = df.columns.intersection(cached_df.columns)
        assert_frame_equal(df[common_columns], cached_df[common_columns], check_like=True)


@pytest.mark.asyncio
async def test_export_to_excel_dataframe_creation_error(
    mock_data_manager, temp_output_dir, mock_formats
):
    with patch.object(pd, "DataFrame", side_effect=ValueError("Test Error")):
        with pytest.raises(PatcherError, match="Encountered error creating DataFrame."):
            await mock_data_manager.export([], temp_output_dir, "Test Report", formats=mock_formats)


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
    with pytest.raises(PatcherError, match="PatchTitles cannot be set to an empty list"):
        data_manager.titles = []


def test_titles_property_setter_valid():
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


# Edge case tests
@pytest.mark.asyncio
async def test_export_to_excel_empty_patch_reports(
    mock_data_manager, temp_output_dir, mock_formats
):
    """Ensure export_excel handles empty patch_reports gracefully."""
    with patch.object(pd, "DataFrame", side_effect=pd.errors.EmptyDataError):
        with pytest.raises(PatcherError, match="Encountered error creating DataFrame"):
            await mock_data_manager.export([], temp_output_dir, "Test Report", formats=mock_formats)


@pytest.mark.asyncio
async def test_export_to_excel_invalid_directory(mock_data_manager, mock_formats):
    """Ensure export_excel raises an error for invalid output directory."""
    invalid_dir = "/invalid/path/to/output"

    with patch.object(mock_data_manager, "_cache_data", return_value=None):
        with patch.object(Path, "mkdir", side_effect=OSError("Test Invalid Directory Error")):
            with pytest.raises(PatcherError, match="Encountered error saving DataFrame"):
                await mock_data_manager.export([], invalid_dir, "Test Report", formats=mock_formats)


@pytest.mark.asyncio
async def test_export_to_excel_permission_error(mock_data_manager, temp_output_path, mock_formats):
    """Simulate a permission error when writing to an output directory."""
    temp_file = temp_output_path / "patch-report.xlsx"

    with patch.object(mock_data_manager, "_cache_data", return_value=None):
        with patch.object(Path, "mkdir", side_effect=PermissionError("Test Permission Error")):
            with pytest.raises(PatcherError, match="Encountered error saving DataFrame"):
                await mock_data_manager.export([], temp_file, "Test Report", formats=mock_formats)


def test_clean_cache_removes_expired_files(temp_output_path):
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
        cache_file.stat.return_value.st_mtime = (datetime.now() - timedelta(days=91)).timestamp()
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


@pytest.mark.asyncio
async def test_load_cached_data_with_corrupted_files(mock_data_manager):
    """Ensure load_cached_data skips corrupted files."""
    corrupted_file = MagicMock(spec=Path)
    corrupted_file.name = "corrupted_cache.pkl"
    corrupted_file.__str__.return_value = "/mocked/path/corrupted_cache.pkl"

    with patch.object(mock_data_manager, "get_cached_files", return_value=[corrupted_file]):
        with patch("pickle.load", side_effect=pickle.UnpicklingError("Test Unpickling error")):
            loaded_data = mock_data_manager.load_cached_data()

    # Assert that no valid data was loaded
    assert len(loaded_data) == 0
