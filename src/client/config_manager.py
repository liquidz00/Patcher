import keyring
from src.model.models import AccessToken, JamfClient
from datetime import datetime, timezone
from src import logger
from pydantic import ValidationError
from typing import Optional

logthis = logger.setup_child_logger("ConfigManager", __name__)


class ConfigManager:
    def __init__(self, service_name: str = "patcher"):
        self.service_name = service_name

    def get_credential(self, key: str) -> str:
        return keyring.get_password(self.service_name, key)

    def set_credential(self, key: str, value: str):
        keyring.set_password(self.service_name, key, value)

    def load_token(self) -> AccessToken:
        token = self.get_credential("TOKEN") or ""
        expires = (
            self.get_credential("TOKEN_EXPIRATION")
            or datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        )
        return AccessToken(token=token, expires=expires)

    def attach_client(self) -> Optional[JamfClient]:
        try:
            return JamfClient(
                client_id=self.get_credential("CLIENT_ID"),
                client_secret=self.get_credential("CLIENT_SECRET"),
                server=self.get_credential("URL"),
                token=self.load_token(),
            )
        except ValidationError as e:
            logthis.error(f"Jamf Client failed validation: {e}")
            return None
