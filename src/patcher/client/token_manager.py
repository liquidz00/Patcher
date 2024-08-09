import asyncio
from datetime import datetime, timedelta, timezone
from typing import AnyStr, Optional, Tuple

from aiohttp import ClientResponseError, ClientSession, TCPConnector

from ..models.jamf_client import JamfClient
from ..models.token import AccessToken
from ..utils import logger
from .config_manager import ConfigManager


class TokenManager:
    """
    Manages the Bearer Token required for accessing the Jamf API.

    The ``TokenManager`` class handles all operations related to the token lifecycle,
    including fetching, saving, and validating the access token. It is initialized
    with a :class:`~patcher.client.config_manager.ConfigManager` instance, which provides the necessary configuration
    and credentials.
    """

    def __init__(self, config: ConfigManager):
        """
        Initializes the TokenManager with a provided ``ConfigManager`` instance.

        :param config: A ``ConfigManager`` instance for managing credentials and configurations.
        :type config: ConfigManager
        :raises ValueError: If the ``JamfClient`` configuration is invalid.
        """
        self.config = config
        self.jamf_client = self.config.attach_client()
        self.log = logger.LogMe(self.__class__.__name__)
        self.log.debug("Initializing TokenManager...")
        if self.jamf_client:
            self.token = self.jamf_client.token
            self.log.info("JamfClient and token successfully attached")
        else:
            self.log.error("Invalid JamfClient configuration was detected and ValueError raised.")
            raise ValueError("Invalid JamfClient configuration detected!")
        self.lock = asyncio.Lock()

    def save_token(self, token: AccessToken):
        """
        Saves the access token and its expiration date securely.

        This method stores the access token and its expiration date in the keyring
        for later retrieval. It also updates the ``JamfClient`` instance with the new token.

        :param token: The ``AccessToken`` instance containing the token and its expiration date.
        :type token: :class:`~patcher.models.token.AccessToken`
        """
        self.log.debug(f"Saving token: {token.token}")
        self.config.set_credential("TOKEN", token.token)
        self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        self.log.info("Bearer token and expiration updated in keyring")
        self.jamf_client.token = token

    def token_valid(self) -> bool:
        """
        Determines if the current access token is still valid.

        This method checks if the token has expired by evaluating its expiration date.

        :return: ``True`` if the token is valid (not expired), otherwise ``False``.
        :rtype: bool
        """
        valid = not self.token.is_expired
        self.log.debug(f"Token validity check: {valid}")
        return valid

    def get_credentials(self) -> Tuple[AnyStr, AnyStr]:
        """
        Retrieves the client ID and client secret for authentication.

        These credentials are required for generating a new access token.

        :return: A tuple containing the client ID and client secret.
        :rtype: Tuple[AnyStr, AnyStr]
        """
        self.log.debug("Retrieving credentials from JamfClient")
        return self.jamf_client.client_id, self.jamf_client.client_secret

    def update_token(self, token_str: AnyStr, expires_in: int):
        """
        Updates the current access token with a new value and expiration time.

        This method is typically called after receiving a new token from the API.

        :param token_str: The new token string.
        :type token_str: AnyStr
        :param expires_in: The number of seconds until the token expires.
        :type expires_in: int
        """
        self.log.debug(
            f"Updating token with new value: {token_str}, expiration: {expires_in} seconds"
        )
        expiration_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token = AccessToken(token=token_str, expires=expiration_time)
        self.save_token(self.token)
        self.log.info("Token updated successfully")

    def check_token_lifetime(self, client: Optional[JamfClient] = None) -> bool:
        """
        Evaluates the remaining lifetime of the access token.

        This method checks if the token's remaining lifetime is sufficient.
        If the lifetime is less than 5 minutes, a warning is issued.

        :param client: The `JamfClient` instance to check the token for. If ``None``,
                       defaults to the current instance.
        :type client: Optional[JamfClient]
        :return: ``True`` if the token's remaining lifetime is more than 5 minutes,
                 otherwise ``False``.
        :rtype: bool
        """
        if client is None:
            client = self.jamf_client

        if not client.token:
            self.log.error(f"No token found for JamfClient {client}")
            return False

        lifetime = client.token.seconds_remaining
        self.log.debug(f"Token lifetime in seconds: {lifetime}")

        if lifetime <= 0:
            self.log.error("Token lifetime is invalid")
            return False

        minutes = lifetime / 60
        self.log.debug(f"Token lifetime in minutes: {minutes}")

        if minutes < 1:
            self.log.error("Token life time is less than 1 minute.")
        elif 5 <= minutes <= 10:
            # Throws warning if token lifetime is between 5-10 minutes
            self.log.warning(
                "Token lifetime is between 5-10 minutes, consider increasing duration."
            )
        else:
            self.log.info(
                f"Token lifetime is sufficient for {client.client_id}. Remaining Lifetime: {client.token.seconds_remaining}"
            )
            return True

    async def fetch_token(self) -> Optional[AccessToken]:
        """
        Asynchronously fetches a new access token from the Jamf API.

        This method sends a request to the Jamf API to obtain a new token.
        The token is then saved and returned for use.

        :return: The fetched ``AccessToken`` instance, or ``None`` if the request fails.
        :rtype: Optional[AccessToken]
        """
        async with self.lock:
            client_id, client_secret = self.get_credentials()
            self.log.debug(f"Using client_id: {client_id}")
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
                        self.log.debug(f"Token response received: {json_response}")
                    except ClientResponseError as e:
                        self.log.error(f"Failed to fetch a token: {e}")
                        return None

                    token = json_response.get("access_token")
                    expires_in = json_response.get("expires_in", 0)

                    if not isinstance(token, str) or expires_in <= 0:
                        self.log.error("Received invalid token response")
                        return None

                    expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    access_token = AccessToken(token=token, expires=expiration)

                    self.save_token(token=access_token)
                    self.log.info("New token fetched and saved successfully")
                    return access_token
