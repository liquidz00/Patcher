from unittest.mock import MagicMock, patch

import pytest
from src.patcher.utils.pdf_report import PDFReport


def test_pdf_init(mock_pdf_report):
    assert mock_pdf_report.ui_config["font_name"] == "Helvetica"
    assert mock_pdf_report.ui_config["header_text"] == "Default header text"


def test_get_image_ratio_valid():
    with patch("PIL.Image.open") as mock_pillow_open:
        mock_image = MagicMock()
        mock_image.size = (100, 50)
        mock_pillow_open.return_value.__enter__.return_value = mock_image

        ratio = PDFReport.get_image_ratio("mock/path/image.png")
        assert ratio == 2.0  # Width-to-height ratio


def test_get_image_ratio_invalid():
    with patch("PIL.Image.open", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            PDFReport.get_image_ratio("mock/path/image.png")


def test_trim_transparency_valid():
    with (
        patch(
            "src.patcher.utils.pdf_report.NamedTemporaryFile", new_callable=MagicMock
        ) as mock_temp,
        patch("PIL.Image.open") as mock_pillow_open,
    ):
        # Mock Image behavior
        mock_image = MagicMock()
        mock_image.getbbox.return_value = (0, 0, 100, 100)
        mock_image.crop.return_value = mock_image
        mock_pillow_open.return_value.__enter__.return_value = mock_image

        # Mock Temporary File
        mock_temp_instance = MagicMock()
        mock_temp_instance.name = "/var/folders/mock/tmp_trimmed.png"
        mock_temp.return_value = mock_temp_instance

        # Call the method
        result = PDFReport.trim_transparency("mock/path/image.png")

        # Assertions
        mock_pillow_open.assert_called_once_with("mock/path/image.png")
        mock_image.getbbox.assert_called_once()
        mock_image.crop.assert_called_once()
        mock_temp.assert_called_once_with(
            delete=False, suffix=".png"
        )  # Validate temp file creation
        assert result == mock_temp_instance.name


def test_trim_transparency_invalid():
    with patch("PIL.Image.open", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            PDFReport.trim_transparency("mock/path/image.png")


def test_header_with_logo_present(mock_pdf_report):
    with (
        patch.object(mock_pdf_report, "trim_transparency", return_value="mock/logo/trimmed.png"),
        patch.object(mock_pdf_report, "get_image_ratio", return_value=2.0),
    ):
        mock_pdf_report.ui_config["logo_path"] = "mock_logo.png"
        mock_pdf_report.add_page()


def test_header_with_no_logo(mock_pdf_report):
    mock_pdf_report.ui_config["logo_path"] = ""
    mock_pdf_report.add_page()


def test_report_footer(mock_pdf_report):
    mock_pdf_report.add_page()
    mock_pdf_report.footer()


def test_report_add_table_header(mock_pdf_report):
    mock_pdf_report.table_headers = ["Column A", "Column B", "Column C"]
    mock_pdf_report.column_widths = [30, 50, 40]

    mock_pdf_report.add_page()
    mock_pdf_report.add_table_header()
