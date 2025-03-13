import plistlib
from pathlib import Path
from unittest.mock import mock_open

import pytest
from src.patcher.client.plist_manager import PropertyListManager
from src.patcher.utils.exceptions import PatcherError


def test_get_existing_section(mock_plist_manager):
    mock_plist_manager.get.return_value = {"header_text": "Header"}
    assert mock_plist_manager.get("UserInterfaceSettings") == {"header_text": "Header"}


def test_get_missing_section(mock_plist_manager):
    mock_plist_manager.get.return_value = None
    assert mock_plist_manager.get("NonExistent") is None


def test_set_new_section(mock_plist_manager):
    mock_plist_manager.set.return_value = None
    mock_plist_manager.set("UserInterfaceSettings", {"header_text": "Header"})
    mock_plist_manager.set.assert_called_with("UserInterfaceSettings", {"header_text": "Header"})


def test_remove_key_from_section(mock_plist_manager):
    mock_plist_manager.remove.return_value = None
    mock_plist_manager.remove("UserInterfaceSettings", "header_text")
    mock_plist_manager.remove.assert_called_with("UserInterfaceSettings", "header_text")


def test_reset_full_plist(mock_plist_manager):
    mock_plist_manager.reset.return_value = True
    assert mock_plist_manager.reset() is True


def test_load_plist_file_valid(mock_plist_manager, mocker, mock_plist):
    mocker.patch.object(mock_plist_manager, "_load_plist_file", return_value=mock_plist)
    assert mock_plist_manager._load_plist_file() == mock_plist


def test_load_plist_file_missing(mocker, tmp_path):
    mocker.patch.object(PropertyListManager, "_ensure_directory", return_value=None)
    plist_manager = PropertyListManager()
    plist_manager.plist_path = tmp_path / "mock_plist.plist"

    mocker.patch.object(Path, "exists", return_value=False)
    assert plist_manager._load_plist_file() == {}


def test_load_plist_file_corrupted(mocker, tmp_path):
    mocker.patch.object(PropertyListManager, "_ensure_directory", return_value=None)
    plist_manager = PropertyListManager()
    plist_manager.plist_path = tmp_path / "mock_plist.plist"
    mocker.patch("plistlib.load", side_effect=plistlib.InvalidFileException)
    assert plist_manager._load_plist_file() == {}


def test_write_plist_file_success(mocker, tmp_path, mock_plist):
    mocker.patch.object(PropertyListManager, "_ensure_directory", return_value=None)
    plist_manager = PropertyListManager()
    plist_manager.plist_path = tmp_path / "mock_plist.plist"
    mock_open_instance = mock_open()
    mocker.patch.object(Path, "open", mock_open_instance)

    mock_plistlib_dump = mocker.patch("plistlib.dump")
    plist_manager._write_plist_file(mock_plist)

    mock_open_instance.assert_called_once_with("wb")
    mock_plistlib_dump.assert_called_once_with(mock_plist, mock_open_instance())


def test_write_plist_file_error(mocker, tmp_path, mock_plist):
    mocker.patch.object(PropertyListManager, "_ensure_directory", return_value=None)
    plist_manager = PropertyListManager()
    plist_manager.plist_path = tmp_path / "mock_plist.plist"

    mocker.patch.object(Path, "open", side_effect=PermissionError("Write access denied"))
    with pytest.raises(PatcherError, match="Could not write to plist file."):
        plist_manager._write_plist_file(mock_plist)
