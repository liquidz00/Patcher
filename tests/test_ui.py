from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from src.patcher.client.ui_manager import UIConfigManager
from src.patcher.utils.exceptions import PatcherError, ShellCommandError


@pytest.fixture
def ui_manager():
    return UIConfigManager()


def test_load_plist_file_valid(ui_manager):
    mock_data = {"UI": {"HEADER_TEXT": "Header", "FOOTER_TEXT": "Footer"}}
    with (
        patch.object(Path, "open", mock_open(read_data=b"<plist>...")) as mock_file,
        patch("plistlib.load", return_value=mock_data) as mock_plist,
    ):
        result = ui_manager._load_plist_file()
        assert result == mock_data
        mock_file.assert_called_once()
        mock_plist.assert_called_once()


def test_load_plist_file_missing(ui_manager):
    with patch.object(Path, "exists", return_value=False):
        result = ui_manager._load_plist_file()
        assert result == {}


def test_load_plist_file_corrupted(ui_manager):
    with (
        patch.object(Path, "open", mock_open(read_data=b"<plist>...")),
        patch("plistlib.load", side_effect=Exception("Invalid format")),
    ):
        result = ui_manager._load_plist_file()
        assert result == {}


def test_write_plist_file_success(ui_manager):
    mock_data = {"UI": {"HEADER_TEXT": "Header", "FOOTER_TEXT": "Footer"}}
    with patch.object(Path, "open", mock_open()) as mock_file, patch("plistlib.dump") as mock_dump:
        ui_manager._write_plist_file(mock_data)
        mock_file.assert_called_once()
        mock_dump.assert_called_once_with(mock_data, mock_file())  # type: ignore


def test_write_plist_file_error(ui_manager):
    with patch.object(Path, "open", side_effect=PermissionError("Permission denied")) as mock_file:
        with pytest.raises(Exception) as excinfo:
            ui_manager._write_plist_file({"UI": {}})
        assert "Permission denied" in str(excinfo.value)
        mock_file.assert_called_once()


def test_fonts_present_both_exist(ui_manager):
    with patch.object(Path, "exists", side_effect=[True, True]):
        assert ui_manager.fonts_present is True


def test_fonts_present_missing(ui_manager):
    with patch.object(Path, "exists", side_effect=[True, False]):
        assert ui_manager.fonts_present is False


def test_config_load_existing(ui_manager):
    mock_data = {"UI": {"HEADER_TEXT": "Header", "FOOTER_TEXT": "Footer"}}
    with (
        patch.object(Path, "exists", side_effect=lambda: True),
        patch("plistlib.load", return_value=mock_data),
        patch.object(ui_manager, "_download_font", MagicMock()),
    ):
        assert ui_manager.config == mock_data["UI"]


def test_config_load_default(ui_manager):
    with (
        patch.object(Path, "exists", side_effect=lambda: False),
        patch.object(ui_manager, "_download_font", MagicMock()),
        patch("plistlib.load", return_value={}),
    ):
        config = ui_manager.config
        assert config["FONT_REGULAR_PATH"].endswith("Assistant-Regular.ttf")
        assert config["FONT_BOLD_PATH"].endswith("Assistant-Bold.ttf")


def test_download_font_success(ui_manager):
    with (patch.object(ui_manager.api, "execute_sync", return_value=b"Success") as mock_exec,):
        ui_manager._download_font("http://example.com/font.ttf", Path("/mock/path/font.ttf"))

        mock_exec.assert_called_once_with(
            ["/usr/bin/curl", "-sL", "http://example.com/font.ttf", "-o", "/mock/path/font.ttf"]
        )


def test_download_font_failure(ui_manager):
    with (
        patch.object(Path, "mkdir"),
        patch.object(
            ui_manager.api, "execute_sync", side_effect=ShellCommandError("Command failed")
        ),
    ):
        with pytest.raises(PatcherError, match="Failed to download default font family"):
            ui_manager._download_font("http://example.com/font.ttf", Path("/mock/path/font.ttf"))


def test_reset_config_success(ui_manager):
    with (
        patch("plistlib.dump"),
        patch.object(Path, "open", mock_open(read_data=b"<plist>...")),
    ):
        assert ui_manager.reset_config() is True


def test_reset_config_failure(ui_manager):
    with patch.object(ui_manager, "_load_plist_file", side_effect=Exception("Unexpected error")):
        assert ui_manager.reset_config() is False


def test_get_with_fallback(ui_manager):
    ui_manager._config = {"HEADER_TEXT": "Header"}
    assert ui_manager.config.get("HEADER_TEXT") == "Header"
    assert ui_manager.config.get("FOOTER_TEXT", "Default Footer") == "Default Footer"
