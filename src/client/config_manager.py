import keyring
import configparser
import os

from typing import Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT_DIR, "fonts")

class ConfigManager:

    def __init__(self, service_name: str = "patcher"):
        self.service_name = service_name
        self.config = configparser.ConfigParser()

        # Paths
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

    def get_credential(self, key: str) -> str:
        return keyring.get_password(self.service_name, key)

    def set_credential(self, key: str, value: str):
        keyring.set_password(self.service_name, key, value)

    def get_ui_config(self) -> Dict:
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
