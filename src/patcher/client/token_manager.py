import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..models.token import AccessToken
from ..utils import exceptions, logger
from . import BaseAPIClient
from .config_manager import ConfigManager


class TokenManager:
    """
    Manages the Bearer Token required for accessing the Jamf API.

    The ``TokenManager`` class handles all operations related to the token lifecycle,
    including fetching, saving, and validating the access token. It is initialized
    with a :class:`~patcher.client.config_manager.ConfigManager` instance, which provides the necessary credentials.
    """

    def __init__(self, config: ConfigManager):
        """
        Initializes the TokenManager with a provided ``ConfigManager`` instance.

        :param config: A ``ConfigManager`` instance for managing credentials and configurations.
        :type config: ConfigManager
        :raises ValueError: If the ``JamfClient`` configuration is invalid.
        """
        self.log = logger.LogMe(self.__class__.__name__)
        self.config = config
        self.api_client = BaseAPIClient()
        self._client = None  # avoid loading credentials at init
        self._token = None
        self.lock = asyncio.Lock()

    @property
    def client(self):
        if not self._client:
            self._client = self.config.attach_client()
            if not self._client:
                raise ValueError("Invalid JamfClient configuration detected.")
            self.log.info(f"JamfClient initialized with base URL: {self._client.base_url}")
        return self._client

    @property
    def token(self) -> AccessToken:
        if not self._token:
            self._token = self.client.token
            self.log.info("Token loaded successfully from JamfClient.")
        return self._token

    async def fetch_token(self) -> Optional[AccessToken]:
        """
        Asynchronously fetches a new access token from the Jamf API.

        This method sends a request to the Jamf API to obtain a new token.
        The token is then saved and returned for use.

        :return: The fetched ``AccessToken`` instance, or ``None`` if the request fails.
        :rtype: Optional[AccessToken]
        """
        client_id, client_secret = self.client.client_id, self.client.client_secret
        url = f"{self.client.base_url}/api/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        data = {
            "client_id": client_id,
            "grant_type": "client_credentials",
            "client_secret": client_secret,
        }

        try:
            response = await self.api_client.fetch_json(
                url, headers=headers, method="POST", data=data
            )
        except exceptions.APIResponseError as e:
            self.log.error(f"Failed to fetch a token from {url}: {e}")
            raise  # Raise same exception that was caught

        return self._parse_token_response(response)

    def _parse_token_response(self, response: Dict) -> Optional[AccessToken]:
        token = response.get("access_token")
        expires_in = response.get("expires_in", 0)
        if not isinstance(token, str) or expires_in <= 0:
            self.log.error("Received invalid token response")
            return None

        expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        access_token = AccessToken(token=token, expires=expiration)

        self._save_token(token=access_token)
        self.log.info("New token fetched and saved successfully")
        return access_token

    def _save_token(self, token: AccessToken):
        """
        Saves the access token and its expiration date securely.

        This method stores the access token and its expiration date in the keyring
        for later retrieval. It also updates the ``JamfClient`` instance with the new token.

        :param token: The ``AccessToken`` instance containing the token and its expiration date.
        :type token: :class:`~patcher.models.token.AccessToken`
        """
        self.config.set_credential("TOKEN", token.token)
        self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        self.client.token = token
        self._token = token  # cache token locally
        self.log.info("Bearer token and expiration updated in keyring")

    def token_valid(self) -> bool:
        """
        Determines if the current access token is still valid.

        This method checks if the token has expired by evaluating its expiration date.

        :return: ``True`` if the token is valid (not expired), otherwise ``False``.
        :rtype: bool
        """
        return not self.token.is_expired

    async def ensure_valid_token(self):
        """
        Verifies the current access token is valid (present and not expired).
        If the token is found to be invalid, a new token is requested and refreshed.

        :raises TokenFetchError: If a new token was unable to be retrieved
        :raises TokenLifetimeError: If the token's remaining lifetime is insufficient.
        """
        async with self.lock:
            if not self.token_valid():
                self.log.warning("Bearer token is invalid or expired, attempting to refresh...")
                if not await self.fetch_token():
                    raise exceptions.TokenFetchError(reason="Unable to validate or refresh token.")
            self.log.info("Token retrieved successfully")
            if not self._check_token_lifetime():
                raise exceptions.TokenLifetimeError(lifetime=self.token.seconds_remaining)

    def _check_token_lifetime(self) -> bool:
        """
        Evaluates the remaining lifetime of the access token.

        This method checks if the token's remaining lifetime is sufficient.
        If the lifetime is less than 2 minutes, a warning is issued.

        :return: ``True`` if the token's remaining lifetime is more than 5 minutes,
                 otherwise ``False``.
        :rtype: bool
        """
        lifetime = self.token.seconds_remaining

        match lifetime:
            case _ if lifetime <= 0:
                self.log.error("Token lifetime is invalid")
                return False
            case _ if lifetime < 120:
                self.log.warning(
                    "Token lifetime is between 5-10 minutes, consider increasing duration."
                )
                return False
            case _ if lifetime > 120:
                self.log.info(f"Token lifetime is sufficient. Remaining Lifetime: {lifetime}")
                return True
            case _:
                self.log.error(f"Unrecognized lifetime provided: {lifetime}")
                return False
