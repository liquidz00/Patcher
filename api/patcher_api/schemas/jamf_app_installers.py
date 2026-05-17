"""
Pydantic schemas for the Jamf App Installers catalog.

The upstream catalog is an HTML table at
``https://learn.jamf.com/...`` with three columns: Title Name, Source,
Host Name. We normalize the Jamf-hosted ``"--"`` placeholder to ``None``
at ingest, so ``host`` is always either a real domain or absent.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class JamfAppInstallerRow(BaseModel):
    """One row parsed out of the upstream HTML table."""

    model_config = ConfigDict(extra="ignore")

    title: str
    source: Literal["Jamf", "External"]
    host: str | None = None
