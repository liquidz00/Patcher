import asyncio
from aiohttp import ClientSession, ClientResponseError, TCPConnector
from typing import AnyStr, Optional
from datetime import datetime, timedelta, timezone
from src import logger
from src.client.config_manager import ConfigManager
from src.model.models import AccessToken, JamfClient

logthis = logger.setup_child_logger("TokenManager", __name__)


class TokenManager:
    """Manages the Bearer Token for accessing the Jamf API."""

    def __init__(self, config: ConfigManager):
        """
        Initialies the TokenManager with the provided ConfigManager.

        :param config: Instance of ConfigManager for loading and storing credentials.
        :type config: ConfigManager
        :raises ValueError: If the JamfClient configuration is invalid.
        """
        self.config = config
        self.jamf_client = self.config.attach_client()
        if self.jamf_client:
            self.token = self.jamf_client.token
        else:
            raise ValueError("Invalid JamfClient configuration detected!")
        self.lock = asyncio.Lock()

    def save_token(self, token: AccessToken):
        """
        Saves the token and its expiration date in the keyring.

        :param token: The access token to save.
        :type token: AccessToken
        """
        self.config.set_credential("TOKEN", token.token)
        self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        logthis.info("Bearer token and expiration updated in keyring")
        self.jamf_client.token = token

    def token_valid(self) -> bool:
        """
        Checks if the current token is valid.

        :return: True if the token is valid, False otherwise.
        :rtype: bool
        """
        return not self.token.is_expired

    def get_credentials(self):
        """
        Retrieves the client ID and client secret from the JamfCLient.

        :return: Tuple containing the client ID and client secret.
        :rtype: tuple
        """
        return self.jamf_client.client_id, self.jamf_client.client_secret

    def update_token(self, token_str: AnyStr, expires_in: int):
        """
        Updates the token with a new value and expiration time.

        :param token_str: The new token string.
        :type token_str: AnyStr
        :param expires_in: The number of seconds until the token expires.
        :type expires_in: int
        """
        expiration_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token = AccessToken(token=token_str, expires=expiration_time)
        self.save_token(self.token)

    def check_token_lifetime(self, client: Optional[JamfClient] = None) -> bool:
        """
        Checks the remaining lifetime of the token.

        :param client: The JamfClient to check the token for, defaults to the current JamfClient.
        :type client: Optional[JamfClient]
        :return: True if the token lifetime is sufficient (greater than 5 mins),
            False otherwise.
        :rtype: bool
        """
        if client is None:
            client = self.jamf_client

        if not client.token:
            logthis.error(f"No token found for JamfClient {client}")
            return False

        lifetime = client.token.seconds_remaining

        if lifetime <= 0:
            logthis.error("Token lifetime is invalid")
            return False

        minutes = lifetime / 60

        if minutes < 1:
            logthis.error("Token life time is less than 1 minute.")
        elif 5 <= minutes <= 10:
            # Throws warning if token lifetime is between 5-10 minutes
            logthis.warning(
                "Token lifetime is between 5-10 minutes, consider increasing duration."
            )
        else:
            logthis.info(
                f"Token lifetime is sfficient for {client.client_id}. Remaining Lifetime: {client.token.seconds_remaining}"
            )
            return True

    async def fetch_token(self) -> Optional[AccessToken]:
        """
        Asynchronously fetches a new token from the Jamf API.

        :return: The fetched access token, or None if fetching fails.
        :rtype: Optional[AccessToken]
        """
        async with self.lock:
            client_id, client_secret = self.get_credentials()
            connector = TCPConnector(limit=self.jamf_client.max_concurrency)
            async with ClientSession(connector=connector) as session:
                payload = {
                    "client_id": client_id,
                    "grant_type": "client_credentials",
                    "client_secret": client_secret,
                }
                headers = {"Content-Type": "application/x-www-form-urlencoded"}

                async with session.post(
                    url=f"{self.jamf_client.base_url}/api/oauth/token",
                    data=payload,
                    headers=headers,
                ) as resp:
                    try:
                        resp.raise_for_status()
                        json_response = await resp.json()
                    except ClientResponseError as e:
                        logthis.error(f"Failed to fetch a token: {e}")
                        return None

                    token = json_response.get("access_token")
                    expires_in = json_response.get("expires_in", 0)

                    if not isinstance(token, str) or expires_in <= 0:
                        logthis.error("Received invalid token response")
                        return None

                    expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    access_token = AccessToken(token=token, expires=expiration)

                    self.save_token(token=access_token)
                    return access_token
