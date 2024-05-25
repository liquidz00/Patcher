import os
from dotenv import load_dotenv

# Global paths
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BIN_DIR)
FONT_DIR = os.path.join(ROOT_DIR, "fonts")
TESTS_DIR = os.path.join(ROOT_DIR, "tests")
ENV_PATH = os.path.join(ROOT_DIR, ".env")

# Global environment variables
load_dotenv(dotenv_path=ENV_PATH)
JAMF_URL = os.getenv("URL")
JAMF_CLIENT_ID = os.getenv("CLIENT_ID")
JAMF_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
JAMF_TOKEN = os.getenv("TOKEN")

# Headers for API Calls
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {JAMF_TOKEN}"}
