from unittest.mock import MagicMock, patch

import pytest
from src.patcher.core.pdf_report import PDFReport


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
            "src.patcher.core.pdf_report.NamedTemporaryFile", new_callable=MagicMock
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


# Document-level rendering: write the full PDF and assert on bytes/page count so
# a rendering-pipeline regression (fonts, multi-page, output) fails a test.


def _make_pdf(ui_config: dict | None = None) -> PDFReport:
    """Bare PDFReport instance with table headers/widths already set."""
    pdf = PDFReport(ui_config=ui_config)
    pdf.table_headers = ["Title", "Hosts Patched", "Missing", "Released"]
    pdf.column_widths = [100, 60, 60, 60]
    return pdf


def _add_table_rows(pdf: PDFReport, n_rows: int) -> None:
    """Add N rows to the PDF so multi-page rendering can be exercised."""
    pdf.set_font(pdf.ui_config["font_name"], "", 10)
    for i in range(n_rows):
        for width in pdf.column_widths:
            pdf.cell(width, 8, f"row {i}", border=1)
        pdf.ln(8)


def test_document_writes_valid_pdf_to_disk(tmp_path):
    """End-to-end: PDFReport instantiates, accepts rows, writes a real PDF."""
    out = tmp_path / "report.pdf"
    pdf = _make_pdf()
    pdf.add_page()
    _add_table_rows(pdf, 5)
    pdf.output(str(out))

    assert out.exists()
    contents = out.read_bytes()
    assert contents.startswith(b"%PDF-"), f"not a PDF: starts with {contents[:8]!r}"
    # Non-trivial size — header + 5 rows + footer
    assert len(contents) > 1000
    assert pdf.page_no() == 1


def test_document_paginates_when_rows_overflow_one_page(tmp_path):
    """Enough rows to force a page break: ``page_no()`` should advance, and
    ``add_table_header`` re-fires on page 2 via the ``header()`` hook."""
    out = tmp_path / "long_report.pdf"
    pdf = _make_pdf()
    pdf.add_page()
    # Landscape A4 has ~190mm usable height; 8mm per row → ~24 rows per page.
    # 60 rows guarantees at least two page breaks.
    _add_table_rows(pdf, 60)
    pdf.output(str(out))

    assert out.exists()
    assert pdf.page_no() >= 2, "expected pagination after 60 rows"
    # Sanity: PDF still valid
    assert out.read_bytes().startswith(b"%PDF-")


def test_init_falls_back_to_helvetica_when_font_paths_missing(tmp_path):
    """Custom font paths that don't exist on disk should not crash; the PDF
    falls back to fpdf's built-in Helvetica."""
    bogus_config = {
        "header_text": "Test",
        "footer_text": "Footer",
        "font_name": "Assistant",  # would-be custom font name
        "reg_font_path": str(tmp_path / "does-not-exist-reg.ttf"),
        "bold_font_path": str(tmp_path / "does-not-exist-bold.ttf"),
        "logo_path": "",
        "header_color": "#6432bdff",
    }
    pdf = PDFReport(ui_config=bogus_config)
    # Fallback overwrites font_name when the on-disk check fails.
    assert pdf.ui_config["font_name"] == "Helvetica"

    # Document should still write successfully via the built-in font.
    out = tmp_path / "fallback.pdf"
    pdf.table_headers = ["A"]
    pdf.column_widths = [100]
    pdf.add_page()
    pdf.output(str(out))
    assert out.read_bytes().startswith(b"%PDF-")
