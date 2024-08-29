from typing import AnyStr, List, Optional

from pydantic import field_validator

from . import Model


class AppTitle(Model):
    title: AnyStr
    bundle_id: Optional[AnyStr] = None
    team_id: Optional[AnyStr] = None
    mas: Optional[bool] = False  # Mac App Store
    cves: Optional[List] = None
    installomator_label: Optional[AnyStr] = None
    jamf_supported: Optional[bool] = False

    @classmethod
    @field_validator("team_id", mode="before")
    def check_team_id(cls, v):
        if len(v) != 10:
            raise ValueError("team_id must be exactly 10 characters long.")
        return v
