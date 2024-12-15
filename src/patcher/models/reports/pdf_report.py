import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Union

import pandas as pd
from fpdf import FPDF
from pandas.errors import ParserError
from PIL import Image

from ...client.ui_manager import UIConfigManager
from ...utils import exceptions, logger


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
        self.log = logger.LogMe(self.__class__.__name__)
        super().__init__(orientation=orientation, unit=unit, format=format)  # type: ignore
        self.date_format = date_format
        self.ui_config = ui_config.get_ui_config()
        self.logo_path = ui_config.get_logo_path()

        self.add_font(self.ui_config.get("FONT_NAME"), "", self.ui_config.get("FONT_REGULAR_PATH"))
        self.add_font(self.ui_config.get("FONT_NAME"), "B", self.ui_config.get("FONT_BOLD_PATH"))

        self.table_headers = []
        self.column_widths = []

    @staticmethod
    def get_image_ratio(image_path: str) -> float:
        """
        Gets the aspect ratio of the logo provided.

        :param image_path: Path to the image file
        :type image_path: str
        :return: The width-to-height ratio of the image.
        :rtype: float
        """
        with Image.open(image_path) as img:
            width, height = img.size
            return width / height

    @staticmethod
    def trim_transparency(image_path: str) -> str:
        """
        Trims transparent padding from the logo and returns the path to a temporary file.

        :param image_path: Path to the input image file.
        :type image_path: str
        :return: Path to the trimmed image.
        :rtype: str
        """
        with Image.open(image_path) as img:
            bbox = img.getbbox()
            trimmed = img.crop(bbox)
            temp_file = NamedTemporaryFile(delete=False, suffix=".png")
            trimmed.save(temp_file.name)
            return temp_file.name

    def header(self):
        """
        Creates the header section for each page of the PDF report with an optional logo.

        The header includes the configured header text and the current date formatted
        according to ``self.date_format``. On subsequent pages, the table header is also added.
        """
        header_font_size = 24
        date_font_size = 18
        text_padding = 2  # Padding between lines of text

        # Text block height calculation
        header_text_height = header_font_size * 0.352778
        date_text_height = date_font_size * 0.352778
        total_text_height = header_text_height + date_text_height + text_padding

        # Top margin
        top_margin = 10

        # Calculate text block center
        text_block_center_y = top_margin + (total_text_height / 2)

        text_x_offset = 10
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                # Trim the logo and use the trimmed version
                trimmed_logo_path = self.trim_transparency(self.logo_path)
                aspect_ratio = self.get_image_ratio(trimmed_logo_path)

                # Adjust logo dimensions
                logo_height_mm = total_text_height
                logo_width_mm = logo_height_mm * aspect_ratio

                # Center the logo vertically
                logo_x = 10
                logo_y = text_block_center_y - (logo_height_mm / 2)
                self.image(trimmed_logo_path, x=logo_x, y=logo_y, w=logo_width_mm, h=logo_height_mm)

                # Adjust text x-offset
                text_x_offset = logo_x + logo_width_mm + 2  # Reduced padding after logo

            except Exception as e:
                self.log.error(f"Error adding logo to header: {e}")

        # Align header text
        self.set_xy(text_x_offset, top_margin)
        self.set_font(self.ui_config.get("FONT_NAME"), "B", header_font_size)
        self.cell(0, header_text_height, self.ui_config.get("HEADER_TEXT"), align="L", ln=True)

        # Align date below header text
        self.set_x(text_x_offset)
        self.set_font(self.ui_config.get("FONT_NAME"), "", date_font_size)
        self.cell(
            0, date_text_height, datetime.now().strftime(self.date_format), align="L", ln=True
        )

        # Add table header for pages > 1
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

    def calculate_column_widths(self, data: pd.DataFrame) -> List[float]:
        """
        Calculates column widths based on the longer of the header length or the longest content in each column,
        ensuring they fit within the page width.

        :param data: DataFrame containing dataset to be included in PDF.
        :type data: pandas.DataFrame
        :return: A list of column widths proportional to header lengths.
        :rtype: List[float]
        """
        # Assign widths based on header lengths
        page_width = self.w - 20  # Account for left/right margins
        max_lengths = [
            max(len(str(header)), data[column].astype(str).map(len).max())
            for header, column in zip(self.table_headers, data.columns)
        ]
        total_length = sum(max_lengths)

        # Calculate proportional widths
        proportional_widths = [(length / total_length) * page_width for length in max_lengths]

        # Enforce constraints to ensure columns fit the page
        while sum(proportional_widths) > page_width:
            excess = sum(proportional_widths) - page_width
            for i in range(len(proportional_widths)):
                if proportional_widths[i] > 20:  # Avoid shrinking below a minimum width
                    adjustment = min(excess, proportional_widths[i] - 20)
                    proportional_widths[i] -= adjustment
                    excess -= adjustment
                    if excess <= 0:
                        break

        return proportional_widths

    def export_excel_to_pdf(
        self, excel_file: Union[str, Path], date_format: str = "%B %d %Y"
    ) -> None:
        """
        Creates a PDF report from an Excel file containing patch data.

        This method reads an Excel file, extracts the data, and populates it into a PDF
        report using the defined headers and column widths. The PDF is then saved to
        the same directory as the Excel file.

        :param excel_file: Path to the Excel file to convert to PDF.
        :type excel_file: Union[str, Path]
        :param date_format: The date format string for the PDF report header.
        :type date_format: str
        """
        # Read excel file
        try:
            df = pd.read_excel(excel_file)
        except ParserError as e:
            self.log.error(f"Failed to parse the excel file: {e}")
            raise exceptions.PatcherError(f"Failed to parse the excel file: {e}")

        # Create instance of FPDF
        pdf = PDFReport(ui_config=UIConfigManager(), date_format=date_format)

        # Set headers and calculate column widths
        pdf.table_headers = df.columns.tolist()
        pdf.column_widths = pdf.calculate_column_widths(df)

        pdf.add_page()
        pdf.add_table_header()

        # Data rows
        pdf.set_font(self.ui_config.get("FONT_NAME"), "", 9)
        for _, row in df.iterrows():
            for data, width in zip(row.astype(str), pdf.column_widths):
                pdf.cell(width, 10, str(data), border=1, align="C")
            pdf.ln(10)
            if pdf.get_y() > pdf.h - 20:
                pdf.add_page()
                pdf.add_table_header()

        # Save PDF to a file
        pdf_filename = os.path.splitext(excel_file)[0] + ".pdf"
        try:
            pdf.output(pdf_filename)
        except (OSError, PermissionError) as e:
            self.log.error(f"Error occurred trying to export to PDF: {e}")
            raise exceptions.ExportError(file_path=pdf_filename)
