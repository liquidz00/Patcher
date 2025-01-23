from unittest.mock import ANY, MagicMock, patch

import pandas as pd
import pytest
from src.patcher.utils.exceptions import PatcherError
from src.patcher.utils.pdf_report import PDFReport


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


def test_header_with_logo():
    pdf = PDFReport()
    pdf.logo_path = "mock/path/logo.png"
    with (
        patch("os.path.exists", return_value=True),
        patch("src.patcher.utils.pdf_report.UIConfigManager") as mock_ui_manager,
        patch.object(
            PDFReport, "trim_transparency", return_value="mock/path/trimmed_logo.png"
        ) as mock_trim,
        patch.object(PDFReport, "get_image_ratio", return_value=2.0),
        patch.object(pdf, "image") as mock_image,
        patch.object(pdf, "cell"),
    ):
        # Properly mock plist
        mock_ui = mock_ui_manager.return_value
        mock_ui.config.return_value = {
            "FONT_NAME": "Helvetica",
            "FONT_REGULAR_PATH": "mock/path/regular_font.ttf",
            "FONT_BOLD_PATH": "mock/path/bold_font.ttf",
            "HEADER_TEXT": "Header Text",
            "FOOTER_TEXT": "Footer Text",
        }
        mock_ui.get_logo_path.return_value = "mock/path/logo.png"
        pdf.header()
        mock_trim.assert_called_once_with("mock/path/logo.png")
        mock_image.assert_called_once()


def test_header_without_logo():
    with (
        patch("src.patcher.utils.pdf_report.UIConfigManager") as mock_ui_manager,
        patch("fpdf.FPDF.add_font") as mock_add_font,
        patch.object(PDFReport, "cell") as mock_cell,
    ):
        mock_ui = mock_ui_manager.return_value
        mock_ui.config = {
            "FONT_NAME": "Helvetica",
            "FONT_REGULAR_PATH": "mock/path/regular_font.ttf",
            "FONT_BOLD_PATH": "mock/path/bold_font.ttf",
            "HEADER_TEXT": "Header Text",
            "FOOTER_TEXT": "Footer Text",
        }
        mock_ui.get_logo_path.return_value = ""

        pdf = PDFReport()
        pdf.add_page()
        pdf.header()

        mock_add_font.assert_any_call("Helvetica", "", "mock/path/regular_font.ttf")
        mock_add_font.assert_any_call("Helvetica", "B", "mock/path/bold_font.ttf")

        mock_cell.assert_any_call(0, ANY, "Header Text", align="L", ln=True)


def test_footer():
    with (
        patch("src.patcher.utils.pdf_report.UIConfigManager") as mock_ui_manager,
        patch("fpdf.FPDF.add_font") as mock_add_font,
        patch.object(PDFReport, "cell") as mock_cell,
    ):
        # Mock UIConfigManager behavior
        mock_ui = mock_ui_manager.return_value
        mock_ui.config = {
            "FONT_NAME": "Helvetica",
            "FONT_REGULAR_PATH": "mock/path/regular_font.ttf",
            "FONT_BOLD_PATH": "mock/path/bold_font.ttf",
            "HEADER_TEXT": "Header Text",
            "FOOTER_TEXT": "Footer Text",
        }
        mock_ui.get_logo_path.return_value = ""

        # Create PDFReport instance and call footer
        pdf = PDFReport()
        pdf.add_page()  # Ensure a page is added
        pdf.footer()

        # Validate font addition
        mock_add_font.assert_any_call("Helvetica", "", "mock/path/regular_font.ttf")
        mock_add_font.assert_any_call("Helvetica", "B", "mock/path/bold_font.ttf")

        # Validate footer cell rendering
        mock_cell.assert_any_call(0, 10, "Footer Text | Page 1", 0, 0, "R")


def test_add_table_header():
    pdf = PDFReport()
    pdf.table_headers = ["Column1", "Column2"]
    pdf.column_widths = [50, 50]
    pdf.add_page()
    with patch.object(pdf, "cell") as mock_cell:
        pdf.add_table_header()
        mock_cell.assert_any_call(50, 10, "Column1", border=1, align="C")
        mock_cell.assert_any_call(50, 10, "Column2", border=1, align="C")


def test_calculate_column_widths():
    pdf = PDFReport()
    data = pd.DataFrame({"Col1": ["A", "BB"], "Col2": ["CCC", "D"]})
    pdf.table_headers = ["Col1", "Col2"]
    widths = pdf.calculate_column_widths(data)
    assert sum(widths) <= pdf.w - 20  # Fit within page width


def test_export_excel_to_pdf_success():
    mock_data = pd.DataFrame({"Col1": ["A", "B"], "Col2": ["C", "D"]})

    with (
        patch("pandas.read_excel", return_value=mock_data),
        patch("os.path.exists", return_value=True),
        patch("fpdf.FPDF.output") as mock_output,
        patch("src.patcher.utils.pdf_report.UIConfigManager") as mock_ui_manager,
        patch("fpdf.FPDF.add_font"),  # Prevent font loading
    ):
        # Mock UIConfigManager behavior
        mock_ui = mock_ui_manager.return_value
        mock_ui.config = {
            "FONT_NAME": "Helvetica",
            "FONT_REGULAR_PATH": "path/to/regular/font.ttf",
            "FONT_BOLD_PATH": "path/to/bold/font.ttf",
            "HEADER_TEXT": "Header",
            "FOOTER_TEXT": "Footer",
        }
        mock_ui.get_logo_path.return_value = None

        pdf = PDFReport()
        pdf.export_excel_to_pdf("mock/path/file.xlsx")

        # Assert PDF generation
        mock_output.assert_called_once()


def test_export_excel_to_pdf_empty():
    pdf = PDFReport()
    with patch("pandas.read_excel", side_effect=pd.errors.EmptyDataError):
        with pytest.raises(PatcherError):
            pdf.export_excel_to_pdf("mock/path/file.xlsx")
