from enum import Enum

from pydantic import Field

from . import Model


class UIConfigKeys(str, Enum):
    HEADER = "header_text"
    FOOTER = "footer_text"
    FONT_NAME = "font_name"
    REG_FONT_PATH = "reg_font_path"
    BOLD_FONT_PATH = "bold_font_path"
    LOGO_PATH = "logo_path"
    HEADER_COLOR = "header_color"


class UIDefaults(Model):
    header_text: str = Field(default="Default header text", min_length=1)
    footer_text: str = Field(default="Default footer text", min_length=1)
    font_name: str = Field(default="Assistant", min_length=1)
    reg_font_path: str = Field(default="", min_length=1)
    bold_font_path: str = Field(default="", min_length=1)
    header_color: str = Field(default="#6432bdff", min_length=1)
    logo_path: str = ""

    class Config:
        validate_assignment = True
