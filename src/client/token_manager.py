from aiohttp import ClientSession, ClientResponseError
from typing import AnyStr, Dict, Optional
from datetime import datetime, timedelta, timezone
from src import logger, globals
from src.client.config_manager import ConfigManager
from src.model.models import AccessToken

logthis = logger.setup_child_logger("token_manager", __name__)


class TokenManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.token = self.load_token()

    def load_token(self) -> AccessToken:
        token = self.config.get_credential("TOKEN") or ""
        expires = (
            self.config.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        return AccessToken(token=token, expires=expires)

    def save_token(self, token: AccessToken):
        self.config.set_credential("TOKEN", token.token)
        self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        logthis.info("Bearer token and expiration updated in keyring")

    def token_valid(self) -> bool:
        return not self.token.is_expired

    def get_credentials(self):
        client_id = self.config.get_credential("CLIENT_ID")
        client_secret = self.config.get_credential("CLIENT_SECRET")
        return client_id, client_secret

    def update_token(self, token_str: AnyStr, expires_in: int):
        expiration_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token = AccessToken(token=token_str, expires=expiration_time)
        self.save_token(self.token)

    async def fetch_token(self) -> Optional[AccessToken]:
        client_id, client_secret = self.get_credentials()
        async with ClientSession() as session:
            payload = {
                "client_id": client_id,
                "grant_type": "client_credentials",
                "client_secret": client_secret,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            async with session.post(
                url=f"{self.config.get_credential('URL')}/api/oauth/token",
                data=payload,
                headers=headers,
            ) as resp:
                try:
                    resp.raise_for_status()
                    json_response = await resp.json()
                    token = json_response.get("access_token")
                    expires_in = json_response.get("expires_in", 0)

                    if not isinstance(token, str) or expires_in <= 0:
                        logthis.error("Received invalid token response")
                        return None

                    expiration = datetime.now(timezone.utc) + timedelta(
                        seconds=expires_in
                    )
                    access_token = AccessToken(token=token, expires=expiration)

                    self.save_token(token=access_token)
                    return access_token
                except ClientResponseError as e:
                    logthis.error(f"Failed to fetch a token: {e}")
                    return None

    async def check_token_lifetime(
        self,
        client_id: Optional[AnyStr] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Ensures the bearer token lifetime is valid (longer than 1 minute, ideally above 10 minutes)

        :param client_id: The client ID property to match. Defaults to client_id in keychain.
        :type client_id: AnyStr
        :param headers: The headers for the request.
        :type headers: Dict[str, str]
        :return: True if token lifetime is greater than 5 minutes
        """
        if client_id is None:
            client_id = self.get_credentials()[0]
        if headers is None:
            headers = globals.HEADERS

        async with ClientSession() as session:
            url = f"{self.config.get_credential('URL')}/api/v1/api-integrations"
            try:
                async with session.get(url=url, headers=headers) as resp:
                    resp.raise_for_status()
                    response = await resp.json()
            except ClientResponseError as e:
                logthis.error(f"API error encountered: {e}")
                return False

        if not response:
            logthis.error("Received empty dictionary fetching response.")
            return False

        results = response.get("results")
        if not results:
            logthis.error("Invalid response received from API call.")
            return False

        lifetime = None
        for result in results:
            if result.get("clientId") == client_id:
                lifetime = result.get("accessTokenLifetimeSeconds")
                logthis.info(f"Retrieved token lifetime for {client_id} successfully.")
                break

        if lifetime is None:
            # Client ID not found
            logthis.error(f"No matching Client ID found for {client_id}.")
            return False

        if lifetime <= 0:
            logthis.error("Token lifetime is invalid.")
            return False

        # Calculate duration in different units
        minutes = lifetime / 60
        hours = minutes / 60
        days = hours / 24
        months = days / 30

        # Throw error if duration of lifetime is less than 1 minute
        if minutes < 1:
            logthis.error("Token life time is less than 1 minute.")
            return False
        elif 5 <= minutes <= 10:
            # Throws warning if token lifetime is between 5-10 minutes
            logthis.warning(
                "Token lifetime is between 5-10 minutes, consider increasing duration."
            )
        else:
            # Lifetime duration logged otherwise
            logthis.info(
                f"Token lifetime: {minutes:.2f} minutes, {hours:.2f} hours, {days:.2f} days, {months:.2f} months."
            )
        return True
