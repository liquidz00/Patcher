import configparser
import os
import urllib.request
from typing import AnyStr, Dict
from urllib.error import URLError

from ..utils import logger


class UIConfigManager:
    """Manages the user interface configuration settings (Header & Footer text of the exported PDF class,
    custom font (optional) and font paths)"""

    REGULAR_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf"
    )
    BOLD_FONT_URL = (
        "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf"
    )

    def __init__(self):
        """Initializes the UIConfigManager by loading the UI configuration."""
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        self.user_config_dir = os.path.expanduser("~/Library/Application Support/Patcher")
        self.user_config_path = os.path.join(self.user_config_dir, "config.ini")
        self.font_dir = os.path.join(self.user_config_dir, "fonts")
        self.log = logger.LogMe(self.__class__.__name__)
        self.load_ui_config()

    def download_font(self, url: AnyStr, dest_path: AnyStr):
        """Downloads Assistant font families from specified URL to destination path"""
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        try:
            with urllib.request.urlopen(url=url) as response:
                if response.status == 200:
                    with open(dest_path, "wb") as f:
                        f.write(response.read())
                else:
                    self.log.error(
                        f"Unable to download default fonts! Received status: {response.status}"
                    )
                    raise OSError("Unable to download default fonts.")
        except URLError as e:
            self.log.error(f"Unable to download default fonts: {e}")
            raise OSError(f"Unable to download default fonts: {e}")

    def create_default_config(self):
        """Creates config.ini with default settings."""
        default_config = {
            "Settings": {"patcher_path": self.user_config_dir},
            "UI": {
                "HEADER_TEXT": "Default header text",
                "FOOTER_TEXT": "Default footer text",
                "FONT_NAME": "Assistant",
                "FONT_REGULAR_PATH": "${Settings:patcher_path}/fonts/Assistant-Regular.ttf",
                "FONT_BOLD_PATH": "${Settings:patcher_path}/fonts/Assistant-Bold.ttf",
            },
        }

        # Ensure directory exists
        os.makedirs(self.user_config_dir, exist_ok=True)

        # Download fonts
        self.download_font(
            self.REGULAR_FONT_URL, os.path.join(self.font_dir, "Assistant-Regular.ttf")
        )
        self.download_font(self.BOLD_FONT_URL, os.path.join(self.font_dir, "Assistant-Bold.ttf"))

        # Write default configuration
        with open(self.user_config_path, "w") as configfile:
            self.config.read_dict(default_config)
            self.config.write(configfile)

    def load_ui_config(self):
        """Loads the UI configuration from the default and user configuration files."""
        if not os.path.exists(self.user_config_path):
            self.create_default_config()

        # Load configs
        self.config.read(self.user_config_path)

    def get_ui_config(self) -> Dict:
        """
        Retrieves the UI configuration settings.

        :return: Dictionary containing UI configuration settings.
        :rtype: Dict
        """
        return {
            "HEADER_TEXT": self.config.get("UI", "HEADER_TEXT"),
            "FOOTER_TEXT": self.config.get("UI", "FOOTER_TEXT", fallback="Default footer text"),
            "FONT_NAME": self.config.get("UI", "FONT_NAME", fallback="Assistant"),
            "FONT_REGULAR_PATH": self.config.get(
                "UI",
                "FONT_REGULAR_PATH",
                fallback=os.path.join(self.font_dir, "Assistant-Regular.ttf"),
            ),
            "FONT_BOLD_PATH": self.config.get(
                "UI",
                "FONT_BOLD_PATH",
                fallback=os.path.join(self.font_dir, "Assistant-Bold.ttf"),
            ),
        }

    def get(self, key: AnyStr, fallback: AnyStr = None) -> AnyStr:
        return self.get_ui_config().get(key, fallback)
