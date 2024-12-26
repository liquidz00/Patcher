import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict

from ..models.token import AccessToken
from ..utils.exceptions import APIResponseError, CredentialError, TokenError
from ..utils.logger import LogMe
from . import BaseAPIClient
from .config_manager import ConfigManager


class TokenManager:
    """
    The ``TokenManager`` class handles all operations related to the token lifecycle, including fetching,
    saving, and validating the access token. It is initialized with a :class:`~patcher.client.config_manager.ConfigManager`
    instance, which provides the necessary credentials.
    """

    def __init__(self, config: ConfigManager):
        """
        Initializes the TokenManager with a provided ``ConfigManager`` instance.

        :param config: A ``ConfigManager`` instance for managing credentials and configurations.
        :type config: :class:`~patcher.client.config_manager.ConfigManager`
        """
        self.log = LogMe(self.__class__.__name__)
        self.config = config
        self.api_client = BaseAPIClient()
        self._client = None  # avoid loading credentials at init
        self._token = None
        self.lock = asyncio.Lock()

    @property
    def client(self):
        if not self._client:
            self.log.debug("Attempting to attach JamfClient.")
            self._client = self.config.attach_client()
            self.log.info(f"JamfClient initialized with base URL: {self._client.base_url}")
        return self._client

    @property
    def token(self) -> AccessToken:
        if not self._token:
            self.log.debug("Attempting to load token from JamfClient.")
            self._token = self.client.token
            self.log.info(
                f"Token ending in {self.client.token.token[-4:]}  loaded successfully from JamfClient."
            )
        return self._token

    async def fetch_token(self) -> AccessToken:
        """
        Asynchronously fetches a new access token from the Jamf API. The token is then
        saved and returned for use.

        :return: The fetched ``AccessToken`` instance.
        :rtype: :class:`~patcher.models.token.AccessToken`
        :raises TokenError: If a token cannot be retrieved from the Jamf API.
        """
        self.log.debug("Attempting to fetch new AccessToken.")
        url = f"{self.client.base_url}/api/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        data = {
            "client_id": self.client.client_id,
            "grant_type": "client_credentials",
            "client_secret": self.client.client_secret,
        }

        try:
            response = await self.api_client.fetch_json(
                url, headers=headers, method="POST", data=data
            )
            self.log.info("Received valid response from Jamf API for AccessToken call.")
        except APIResponseError as e:
            self.log.error(f"Failed to fetch a token from {url}. Details: {e}")
            raise TokenError("Unable to retrieve AccessToken from Jamf instance.", url=url) from e

        return self._parse_token_response(response)

    def _parse_token_response(self, response: Dict) -> AccessToken:
        """
        Private method that parses the Jamf API Token response and extracts the
        token string and token expiration.

        :param response: The API response payload from Jamf.
        :type response: Dict
        :return: The extracted ``AccessToken`` object.
        :rtype: :class:`~patcher.models.token.AccessToken`
        """
        self.log.debug("Attempting to parse API response for AccessToken.")
        token = response.get("access_token")
        expires_in = response.get("expires_in")

        expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        access_token = AccessToken(token=token, expires=expiration)

        self._save_token(token=access_token)
        self.log.info("New token fetched and saved successfully")
        return access_token

    def _save_token(self, token: AccessToken):
        """
        This method stores the access token and its expiration date in the keyring
        for later retrieval. It also updates the ``JamfClient`` instance with the new token.

        :param token: The ``AccessToken`` instance containing the token and its expiration date.
        :type token: :class:`~patcher.models.token.AccessToken`
        :raises TokenError: If either the token string or expiration could not be saved.
        """
        self.log.debug("Attempting to save retrieved AccessToken object.")
        try:
            self.config.set_credential("TOKEN", token.token)
            self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        except CredentialError as e:
            self.log.error(f"Unable to save AccessToken object to keychain. Details: {e}")
            raise TokenError("Unable to save AccessToken object to keychain") from e

        self.client.token = token
        self._token = token  # cache token locally
        self.log.info("AccessToken object updated in keychain")

    def token_valid(self) -> bool:
        """
        Determines if the current access token is still valid by evaluating its
        expiration date.

        :return: ``True`` if the token is valid (not expired), otherwise ``False``.
        :rtype: bool
        """
        return not self.token.is_expired

    async def ensure_valid_token(self):
        """
        Verifies the current access token is valid (present and not expired).
        If the token is found to be invalid, a new token is requested and refreshed.

        .. seealso::

            The :meth:`~patcher.utils.decorators.check_token` decorator leverages
            this method with thread locking to ensure tokens are valid before API calls.

        """
        async with self.lock:
            if not self.token_valid():
                self.log.warning("Bearer token is invalid or expired, attempting to refresh...")
                await self.fetch_token()
            self.log.info("Token retrieved successfully")
