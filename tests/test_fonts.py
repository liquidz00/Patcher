from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from src.patcher.core import fonts
from src.patcher.core.exceptions import PatcherError


def test_get_font_paths_uses_dir():
    paths = fonts.get_font_paths(Path("/mock"))
    assert paths["regular"] == Path("/mock/Assistant-Regular.ttf")
    assert paths["bold"] == Path("/mock/Assistant-Bold.ttf")


def test_fonts_present_both_exist():
    with patch.object(Path, "exists", return_value=True):
        assert fonts.fonts_present(Path("/mock")) is True


def test_fonts_present_missing():
    with patch.object(Path, "exists", side_effect=[True, False]):
        assert fonts.fonts_present(Path("/mock")) is False


def test_ensure_default_fonts_skips_when_present(tmp_path):
    with (
        patch.object(fonts, "fonts_present", return_value=True),
        patch("src.patcher.core.fonts.httpx.get") as mock_get,
    ):
        result = fonts.ensure_default_fonts(tmp_path)
        mock_get.assert_not_called()
        assert result == fonts.get_font_paths(tmp_path)


def test_ensure_default_fonts_downloads_when_missing(tmp_path):
    response = MagicMock()
    response.content = b"font-bytes"
    with (
        patch.object(fonts, "fonts_present", return_value=False),
        patch("src.patcher.core.fonts.httpx.get", return_value=response) as mock_get,
    ):
        fonts.ensure_default_fonts(tmp_path)
        assert mock_get.call_count == 2
        assert (tmp_path / "Assistant-Regular.ttf").read_bytes() == b"font-bytes"


def test_ensure_default_fonts_failure_propagates(tmp_path):
    with (
        patch.object(fonts, "fonts_present", return_value=False),
        patch("src.patcher.core.fonts.httpx.get", side_effect=httpx.HTTPError("boom")),
    ):
        with pytest.raises(PatcherError, match="Failed to download default font family"):
            fonts.ensure_default_fonts(tmp_path)


def test_copy_asset_failure_raises():
    with patch("src.patcher.core.fonts.shutil.copy", side_effect=OSError("nope")):
        with pytest.raises(PatcherError, match="Failed to copy file"):
            fonts.copy_asset(Path("/a"), Path("/b"))
