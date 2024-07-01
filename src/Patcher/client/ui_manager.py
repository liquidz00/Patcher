import configparser
import os
from typing import Dict, AnyStr

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(SRC_DIR)
FONT_DIR = os.path.join(ROOT_DIR, "fonts")


class UIConfigManager:
    """Manages the user interface configuration settings (Header & Footer text of the exported PDF class,
    custom font (optional) and font paths)"""

    def __init__(self):
        """Initializes the UIConfigManager by loading the UI configuration."""
        self.config = configparser.ConfigParser()
        self.load_ui_config()

    def load_ui_config(self):
        """Loads the UI configuration from the default and user configuration files."""
        default_path = os.path.join(ROOT_DIR, "config.ini")
        user_config_dir = os.path.expanduser("~/Library/Application Support/Patcher")
        user_config_path = os.path.join(user_config_dir, "config.ini")

        # Ensure directory exists
        os.makedirs(user_config_dir, exist_ok=True)

        # Load configs
        self.config.read(default_path)

        # Override with user configuration if available
        if os.path.exists(user_config_path):
            self.config.read(user_config_path)

    def get_ui_config(self) -> Dict:
        """
        Retrieves the UI configuration settings.

        :return: Dictionary containing UI configuration settings.
        :rtype: Dict
        """
        return {
            "HEADER_TEXT": self.config.get("UI", "HEADER_TEXT"),
            "FOOTER_TEXT": self.config.get(
                "UI", "FOOTER_TEXT", fallback="Default footer text"
            ),
            "FONT_NAME": self.config.get("UI", "FONT_NAME", fallback="Assistant"),
            "FONT_REGULAR_PATH": self.config.get(
                "UI",
                "FONT_REGULAR_PATH",
                fallback=os.path.join(FONT_DIR, "Assistant-Regular.ttf"),
            ),
            "FONT_BOLD_PATH": self.config.get(
                "UI",
                "FONT_BOLD_PATH",
                fallback=os.path.join(FONT_DIR, "Assistant-Bold.ttf"),
            ),
        }

    def get(self, key: AnyStr, fallback: AnyStr = None) -> AnyStr:
        return self.get_ui_config().get(key, fallback)
