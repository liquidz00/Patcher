"""Response schemas for the ``/stats`` catalog-statistics endpoint."""

from datetime import datetime

from pydantic import BaseModel


class SourceCoverage(BaseModel):
    """How many apps carry each upstream source's data."""

    installomator: int
    homebrew_cask: int
    jamf_app_installer: int
    autopkg: int


class CatalogStats(BaseModel):
    """Top-line catalog statistics returned by ``GET /stats``."""

    total_apps: int
    sources: SourceCoverage
    last_refresh: datetime | None
    catalog_version: str | None
