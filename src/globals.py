import os
from src.client.config_manager import ConfigManager

config = ConfigManager()

# Global paths
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BIN_DIR)
FONT_DIR = os.path.join(ROOT_DIR, "fonts")
TESTS_DIR = os.path.join(ROOT_DIR, "tests")
ENV_PATH = os.path.join(ROOT_DIR, ".env")

# Global environment variables
JAMF_URL = config.get_credential("URL")
JAMF_CLIENT_ID = config.get_credential("CLIENT_ID")
JAMF_CLIENT_SECRET = config.get_credential("CLIENT_SECRET")
JAMF_TOKEN = config.get_credential("TOKEN")
JAMF_TOKEN_EXPIRATION = config.get_credential("TOKEN_EXPIRATION")

# Headers for API Calls
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {JAMF_TOKEN}"}
