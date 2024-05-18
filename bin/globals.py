import os

# Global paths
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BIN_DIR)
FONT_DIR = os.path.join(ROOT_DIR, "fonts")
TESTS_DIR = os.path.join(ROOT_DIR, "tests")
ENV_PATH = os.path.join(ROOT_DIR, ".env")
