from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, field_validator, Field


class AccessToken(BaseModel):
    type: str = ""
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

    @field_validator("expires", mode="before")
    def set_expiry(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v
