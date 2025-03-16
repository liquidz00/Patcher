import os
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import List

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

from ..client.ui_manager import UIConfigManager
from ..utils.logger import LogMe


class PDFReport(FPDF):
    def __init__(
        self,
        orientation="L",
        unit="mm",
        format="A4",
        date_format="%B %d %Y",
        ui_config: UIConfigManager = None,
    ):
        """
        The ``PDFReport`` class extends FPDF to create a PDF report from an Excel file containing patch data.

        It supports custom headers, footers, font styles, and an optional branding logo based on the UI configuration.

        :param orientation: Orientation of the PDF, default is "L" (landscape).
        :type orientation: :py:class:`str`
        :param unit: Unit of measurement, default is "mm".
        :type unit: :py:class:`str`
        :param format: Page format, default is "A4".
        :type format: :py:class:`str`
        :param date_format: Date format string for the PDF report header, default is "%B %d %Y".
        :type date_format: :py:class:`str`
        :param ui_config: Optional UIConfigManager object to pass, defaults to initializing new object.
        :type ui_config: :class:`~patcher.client.ui_manager.UIConfigManager`
        """
        self.log = LogMe(self.__class__.__name__)
        super().__init__(orientation=orientation, unit=unit, format=format)  # type: ignore
        self.date_format = date_format
        self.ui = ui_config or UIConfigManager()
        self.ui_config = self.ui.config

        self.table_headers = []
        self.column_widths = []

        self.add_font(self.ui_config.get("font_name"), "", self.ui_config.get("reg_font_path"))
        self.add_font(self.ui_config.get("font_name"), "B", self.ui_config.get("bold_font_path"))

    @staticmethod
    def get_image_ratio(image_path: str) -> float:
        """
        Gets the aspect ratio of the logo provided.

        :param image_path: Path to the image file
        :type image_path: :py:class:`str`
        :return: The width-to-height ratio of the image.
        :rtype: :py:class:`float`
        """
        with Image.open(image_path) as img:
            width, height = img.size
            return width / height

    @staticmethod
    def trim_transparency(image_path: str) -> str:
        """
        Trims transparent padding from the logo and returns the path to a temporary file.

        :param image_path: Path to the input image file.
        :type image_path: :py:class:`str`
        :return: Path to the trimmed image.
        :rtype: :py:class:`str`
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
        text_padding = 2
        top_margin = 10
        text_x_offset = 10

        # Text block height calculation
        header_text_height = header_font_size * 0.352778  # mm
        date_text_height = date_font_size * 0.352778  # mm
        total_text_height = header_text_height + date_text_height + text_padding

        # Calculate text block center
        text_block_center_y = top_margin + (total_text_height / 2)

        # Handle optional logo
        logo_path = self.ui_config.get("logo_path", "")
        if logo_path:
            if not os.path.exists(logo_path):
                self.log.warning(f"Logo file not found: {logo_path}")
            else:
                try:
                    # Trim the logo and use the trimmed version
                    trimmed_logo_path = self.trim_transparency(logo_path)
                except (FileNotFoundError, OSError) as e:
                    self.log.warning(f"Failed to process logo image. Details: {e}")
                    trimmed_logo_path = None
                except ValueError as e:
                    self.log.warning(f"Invalid image dimensions for logo. Details: {e}")
                    trimmed_logo_path = None

                if trimmed_logo_path:
                    try:
                        # Adjust logo dimensions
                        aspect_ratio = self.get_image_ratio(trimmed_logo_path)
                        logo_height_mm = total_text_height
                        logo_width_mm = logo_height_mm * aspect_ratio
                        logo_y = text_block_center_y - (logo_height_mm / 2)
                        self.image(
                            trimmed_logo_path, x=10, y=logo_y, w=logo_width_mm, h=logo_height_mm
                        )
                        text_x_offset = 10 + logo_width_mm + 2  # Reduced padding after logo
                    except RuntimeError as e:
                        self.log.warning(f"Error adding logo to header. Details: {e}")

        # Align header text
        self.set_xy(text_x_offset, top_margin)
        self.set_font(self.ui_config.get("font_name"), "B", header_font_size)
        self.cell(
            0,
            header_text_height,
            self.ui_config.get("header_text"),
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        # Align date below header text
        self.set_x(text_x_offset)
        self.set_font(self.ui_config.get("font_name"), "", date_font_size)
        self.cell(
            0,
            date_text_height,
            datetime.now().strftime(self.date_format),
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
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
        self.set_font(self.ui_config.get("font_name"), "B", 11)
        for header, width in zip(self.table_headers, self.column_widths):
            self.cell(width, 10, header, border=1, align="C")
        self.cell(0, 10, "", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def footer(self):
        """
        Creates the footer section for each page of the PDF report.

        The footer includes the configured footer text and the current page number.
        The footer text is styled with a smaller font and a light gray color.
        """
        self.set_y(-15)
        self.set_font(self.ui_config.get("font_name"), "", 6)
        self.set_text_color(175, 175, 175)
        footer_text = f"{self.ui_config.get('footer_text')} | Page " + str(self.page_no())
        self.cell(0, 10, footer_text, 0, 0, "R")

    def calculate_column_widths(self, data: pd.DataFrame) -> List[float]:
        """
        Calculates column widths based on the longer of the header length or the longest content in each column,
        ensuring they fit within the page width.

        :param data: DataFrame containing dataset to be included in PDF.
        :type data: `pandas.DataFrame <https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html>`_
        :return: A list of column widths proportional to header lengths.
        :rtype: :py:obj:`~typing.List` [:py:class:`float`]
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
