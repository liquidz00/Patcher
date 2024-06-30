from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, field_validator, Field
from urllib.parse import urlparse, urlunparse
from typing import Optional, AnyStr


class AccessToken(BaseModel):
    token: str = ""
    expires: datetime = Field(default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc))

    def __str__(self):
        return self.token

    @property
    def is_expired(self) -> bool:
        return self.expires - timedelta(seconds=60) < datetime.now(timezone.utc)

    @property
    def seconds_remaining(self) -> int:
        return max(0, int((self.expires - datetime.now(timezone.utc)).total_seconds()))


class JamfClient(BaseModel):
    client_id: AnyStr
    client_secret: AnyStr
    server: AnyStr
    token: Optional[AccessToken] = None

    @staticmethod
    def valid_url(url: AnyStr) -> AnyStr:
        parsed_url = urlparse(url=url)
        scheme = "https" if not parsed_url.scheme else parsed_url.scheme
        netloc = (
            parsed_url.netloc if parsed_url.netloc else parsed_url.path.split("/")[0]
        )
        path = (
            "/" + "/".join(parsed_url.path.split("/")[1:])
            if len(parsed_url.path.split("/")) > 1
            else ""
        )
        new_url = urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))
        return new_url.rstrip("/")

    @field_validator("client_id", "client_secret", mode="before")
    def not_empty(cls, value):
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @field_validator("server", mode="before")
    def validate_url(cls, v):
        return cls.valid_url(v)

    @property
    def base_url(self):
        return self.server
