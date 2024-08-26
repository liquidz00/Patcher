import os
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
    @field_validator("mas", mode="before")
    def check_mas(cls, v, values):
        if not v and "name" in values:
            app_path = values["name"]
            mas_receipt_path = os.path.join(app_path, "Contents", "_MASReceipt")
            return os.path.isdir(mas_receipt_path)
        return v
