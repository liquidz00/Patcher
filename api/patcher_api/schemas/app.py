from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl


class InstallMethod(StrEnum):
    """
    Mirrors Installomator's `type` variable.

    See https://github.com/Installomator/Installomator/wiki/Label-Variables-Reference
    for the upstream definition.
    """

    DMG = "dmg"
    PKG = "pkg"
    ZIP = "zip"
    TBZ = "tbz"
    PKG_IN_DMG = "pkgInDmg"
    PKG_IN_ZIP = "pkgInZip"
    APP_IN_DMG_IN_ZIP = "appInDmgInZip"


class App(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    bundle_id: str | None = None
    name: str
    vendor: str
    current_version: str
    latest_release_date: date | None = None
    download_url: HttpUrl
    install_method: InstallMethod
    sha256: str | None = None
    sources: list[str]
    cves: list[str] = []
