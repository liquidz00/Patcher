import os
import configparser
from src import globals

# Paths
ROOT = globals.ROOT_DIR
FONT = globals.FONT_DIR
default_path = os.path.join(ROOT, 'config.ini')
user_config_dir = os.path.expanduser("~/Library/Application Support/Patcher")
user_config_path = os.path.join(user_config_dir, "config.ini")

# Ensure directory exists
os.makedirs(user_config_dir, exist_ok=True)

# Load configs
config = configparser.ConfigParser()
config.read(default_path)

# Override with user configuration if available
if os.path.exists(user_config_path):
    config.read(user_config_path)

# Default UI Configurations
HEADER_TEXT = config.get("UI", "HEADER_TEXT", fallback="Default header text")
FOOTER_TEXT = config.get("UI", "FOOTER_TEXT", fallback="Default footer text")
FONT_NAME = config.get("UI", "FONT_NAME", fallback="Assistant")
FONT_REGULAR_PATH = config.get("UI", "FONT_REGULAR_PATH", fallback=os.path.join(FONT, "Assistant-Regular.ttf"))
FONT_BOLD_PATH = config.get("UI", "FONT_BOLD_PATH", fallback=os.path.join(FONT, "Assistant-Bold.ttf"))
