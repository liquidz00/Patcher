import urllib.parse
from typing import List, Optional

from pydantic import field_validator, model_validator

from . import Model
from .label import Label
from .patch import PatchTitle


class AppTitle(Model):
    title: str
    normalized_title: str
    bundle_id: Optional[str] = None
    mas: Optional[bool] = False  # Mac App Store
    jamf_supported: Optional[bool] = False

    # optional associations
    patches: Optional[List[PatchTitle]]
    labels: Optional[List[Label]]

    @classmethod
    @field_validator("title", mode="before")
    def validate_title(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Title must be a string.")
        return v

    @classmethod
    @model_validator(mode="after")
    def set_normalized_title(cls, values):
        title = values.title
        values.normalized_title = urllib.parse.unquote(title).strip().lower()
        return values

    @classmethod
    @field_validator("team_id", mode="before")
    def check_team_id(cls, v):
        if len(v) != 10:
            raise ValueError("team_id must be exactly 10 characters long.")
        return v
