from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest
from src.patcher.client.ui_manager import UIConfigKeys, UIConfigManager
from src.patcher.utils.exceptions import PatcherError


@pytest.fixture
def ui_manager(mock_plist_manager, monkeypatch):
    with patch("src.patcher.core.ui_manager.PropertylistManager", return_value=mock_plist_manager):
        manager = UIConfigManager()

        monkeypatch.setattr(
            manager,
            "_get_font_paths",
            lambda: {
                "regular": Path("/mock/path/Assistant-Regular.ttf"),
                "bold": Path("/mock/path/Assistant-Bold.ttf"),
            },
        )

        monkeypatch.setattr(manager, "_download_fonts", lambda: None)

        return manager


def test_fonts_present_both_exist(ui_manager):
    with patch.object(Path, "exists", return_value=True):
        assert ui_manager.fonts_present is True


def test_fonts_present_missing(ui_manager):
    with patch.object(Path, "exists", side_effect=[True, False]):
        assert ui_manager.fonts_present is False


def test_config_load_existing(ui_manager, mock_plist_manager):
    mock_data = {
        UIConfigKeys.HEADER.value: "Header",
        UIConfigKeys.FOOTER.value: "Footer",
    }
    mock_plist_manager.get.return_value = mock_data
    assert ui_manager.config == mock_data


def test_config_load_default(ui_manager, mock_plist_manager):
    mock_plist_manager.get.return_value = None

    with patch.object(
        ui_manager, "create_default_config", wraps=ui_manager.create_default_config
    ) as mock_create_default:
        config = ui_manager.config
        mock_create_default.assert_called_once()

        expected_config = {
            UIConfigKeys.HEADER.value: "Default header text",
            UIConfigKeys.FOOTER.value: "Default footer text",
            UIConfigKeys.FONT_NAME.value: "Assistant",
            UIConfigKeys.REG_FONT_PATH.value: "/mock/path/Assistant-Regular.ttf",
            UIConfigKeys.BOLD_FONT_PATH.value: "/mock/path/Assistant-Bold.ttf",
            UIConfigKeys.LOGO_PATH.value: "",
            UIConfigKeys.HEADER_COLOR.value: "#6432bdff",
        }

        assert config == expected_config


def test_download_font_success(ui_manager, monkeypatch):
    monkeypatch.setattr(
        ui_manager, "_download_fonts", UIConfigManager._download_fonts.__get__(ui_manager)
    )

    mock_response = MagicMock(content=b"FontBinaryData")
    mock_response.raise_for_status = MagicMock()

    with (
        patch.object(ui_manager, "fonts_present", new_callable=lambda: False),
        patch("src.patcher.core.ui_manager.httpx.get", return_value=mock_response) as mock_get,
        patch.object(Path, "write_bytes") as mock_write,
    ):
        ui_manager._download_fonts()

        assert mock_get.call_count == 2  # regular, bold
        assert mock_write.call_count == 2
        # Verify both font URLs were fetched
        called_urls = {call.args[0] for call in mock_get.call_args_list}
        assert ui_manager._FONT_URLS["regular"] in called_urls
        assert ui_manager._FONT_URLS["bold"] in called_urls


def test_download_font_failure(ui_manager, monkeypatch):
    monkeypatch.setattr(
        ui_manager, "_download_fonts", UIConfigManager._download_fonts.__get__(ui_manager)
    )
    with (
        patch.object(ui_manager, "fonts_present", new_callable=lambda: False),
        patch(
            "src.patcher.core.ui_manager.httpx.get",
            side_effect=httpx.ConnectError("connect failed"),
        ),
    ):
        with pytest.raises(PatcherError, match="Failed to download default font family"):
            ui_manager._download_fonts()


def test_reset_config_success(ui_manager):
    with (
        patch.object(ui_manager.plist_manager, "remove", return_value=True),
        patch("plistlib.dump"),
        patch.object(Path, "open", mock_open(read_data=b"<plist>...")),
    ):
        assert ui_manager.reset_config() is True


def test_reset_config_failure(ui_manager):
    with patch.object(
        ui_manager.plist_manager, "remove", side_effect=Exception("Unexpected error")
    ):
        assert ui_manager.reset_config() is False
