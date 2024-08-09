import os
from datetime import datetime
from pathlib import Path
from typing import AnyStr, Union

import pandas as pd
from fpdf import FPDF

from ...client.ui_manager import UIConfigManager
from ...utils import logger

logthis = logger.setup_child_logger("PDFReport", __name__)


class PDFReport(FPDF):
    """
    Handles the generation of PDF reports from Excel files.

    The ``PDFReport`` class extends FPDF to create a PDF report from an Excel file
    containing patch data. It supports custom headers, footers, and font styles
    based on the UI configuration.
    """

    def __init__(
        self,
        ui_config: UIConfigManager,
        orientation="L",
        unit="mm",
        format="A4",
        date_format="%B %d %Y",
    ):
        """
        Initializes the PDFReport with the provided parameters and UIConfigManager.

        :param ui_config: An instance of ``UIConfigManager`` for managing UI configuration.
        :type ui_config: UIConfigManager
        :param orientation: Orientation of the PDF, default is "L" (landscape).
        :type orientation: str
        :param unit: Unit of measurement, default is "mm".
        :type unit: str
        :param format: Page format, default is "A4".
        :type format: str
        :param date_format: Date format string for the PDF report header, default is "%B %d %Y".
        :type date_format: str
        """
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.date_format = date_format
        self.ui_config = ui_config.get_ui_config()

        self.add_font(self.ui_config.get("FONT_NAME"), "", self.ui_config.get("FONT_REGULAR_PATH"))
        self.add_font(self.ui_config.get("FONT_NAME"), "B", self.ui_config.get("FONT_BOLD_PATH"))

        self.table_headers = []
        self.column_widths = []

    def header(self):
        """
        Creates the header section for each page of the PDF report.

        The header includes the configured header text and the current date formatted
        according to ``self.date_format``. On subsequent pages, the table header is also added.
        """
        self.set_font(self.ui_config.get("FONT_NAME"), "B", 24)
        self.cell(0, 10, self.ui_config.get("HEADER_TEXT"), new_x="LMARGIN", new_y="NEXT")

        self.set_font(self.ui_config.get("FONT_NAME"), "", 18)
        self.cell(
            0,
            10,
            datetime.now().strftime(self.date_format),
            new_x="LMARGIN",
            new_y="NEXT",
        )

        if self.page_no() > 1:
            self.add_table_header()

    def add_table_header(self):
        """
        Adds the table header to the PDF report.

        This method is called on pages after the first to add column headers for
        the data table in the PDF report. The headers and their widths are defined
        by ``self.table_headers`` and ``self.column_widths``.
        """
        self.set_y(30)
        self.set_font(self.ui_config.get("FONT_NAME"), "B", 11)
        for header, width in zip(self.table_headers, self.column_widths):
            self.cell(width, 10, header, border=1, align="C")
        self.ln(10)

    def footer(self):
        """
        Creates the footer section for each page of the PDF report.

        The footer includes the configured footer text and the current page number.
        The footer text is styled with a smaller font and a light gray color.
        """
        self.set_y(-15)
        self.set_font(self.ui_config.get("FONT_NAME"), "", 6)
        self.set_text_color(175, 175, 175)
        footer_text = f"{self.ui_config.get('FOOTER_TEXT')} | Page " + str(self.page_no())
        self.cell(0, 10, footer_text, 0, 0, "R")

    def export_excel_to_pdf(
        self, excel_file: Union[str, Path], date_format: AnyStr = "%B %d %Y"
    ) -> None:
        """
        Creates a PDF report from an Excel file containing patch data.

        This method reads an Excel file, extracts the data, and populates it into a PDF
        report using the defined headers and column widths. The PDF is then saved to
        the same directory as the Excel file.

        :param excel_file: Path to the Excel file to convert to PDF.
        :type excel_file: Union[str, Path]
        :param date_format: The date format string for the PDF report header.
        :type date_format: AnyStr
        """
        try:
            # Read excel file
            df = pd.read_excel(excel_file)

            # Create instance of FPDF
            pdf = PDFReport(ui_config=UIConfigManager(), date_format=date_format)
            pdf.table_headers = df.columns
            pdf.column_widths = [75, 40, 40, 40, 40, 40]
            pdf.add_page()
            pdf.add_table_header()

            # Data rows
            pdf.set_font(self.ui_config.get("FONT_NAME"), "", 9)
            for index, row in df.iterrows():
                for data, width in zip(row, pdf.column_widths):
                    pdf.cell(width, 10, str(data), border=1, align="C")
                pdf.ln(10)

            # Save PDF to a file
            pdf_filename = os.path.splitext(excel_file)[0] + ".pdf"
            pdf.output(pdf_filename)

        except Exception as e:
            logthis.error(f"Error occurred trying to export PDF: {e}")
