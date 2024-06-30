from aiohttp import ClientSession, ClientResponseError
from typing import AnyStr, Optional
from datetime import datetime, timedelta, timezone
from src import logger
from src.client.config_manager import ConfigManager
from src.model.models import AccessToken, JamfClient

logthis = logger.setup_child_logger("TokenManager", __name__)


class TokenManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.jamf_client = self.config.attach_client()
        if self.jamf_client:
            self.token = self.jamf_client.token
        else:
            raise ValueError("Invalid JamfClient configuration detected!")

    def save_token(self, token: AccessToken):
        self.config.set_credential("TOKEN", token.token)
        self.config.set_credential("TOKEN_EXPIRATION", token.expires.isoformat())
        logthis.info("Bearer token and expiration updated in keyring")
        self.jamf_client.token = token

    def token_valid(self) -> bool:
        return not self.token.is_expired

    def get_credentials(self):
        return self.jamf_client.client_id, self.jamf_client.client_secret

    def update_token(self, token_str: AnyStr, expires_in: int):
        expiration_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token = AccessToken(token=token_str, expires=expiration_time)
        self.save_token(self.token)

    def check_token_lifetime(self, client: Optional[JamfClient] = None) -> bool:
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
        client_id, client_secret = self.get_credentials()
        async with ClientSession() as session:
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
