import aiohttp
import asyncio

from bin import globals, logger
from dotenv import load_dotenv, set_key

logthis = logger.setup_child_logger("patcher", __name__)

# Environment variables
ENV_PATH = globals.ENV_PATH
load_dotenv(dotenv_path=ENV_PATH)

# TODO:
#
# 1. Check API provided has proper privileges
#   (Read Computers, Read Patch   reporting roles)
#       API endpoint: /api/v1/api-role-privileges

# 2. If proper privileges are not found, create them
#   OR create API integration if needed
#       API endpoint: /api/v1/api-integrations

# 3. Increase access token lifetime if too short
#   Unnecessary if creating API integration
#       API endpoint: /api/v1/api-integrations/{id}

# 4. Update .env with new client_id, client_secret, and token if necessary
