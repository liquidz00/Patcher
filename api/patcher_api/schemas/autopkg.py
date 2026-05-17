"""
Pydantic schemas for the AutoPkg recipe index.

Models the subset of fields we project into our ``autopkg_recipes`` table.
Extra fields are intentionally ignored (``extra="ignore"``) so the schema
stays resilient when the upstream index format evolves.

Reference: https://github.com/autopkg/index/blob/main/index.json
"""

from pydantic import BaseModel, ConfigDict


class AutopkgIndexEntry(BaseModel):
    """
    A single recipe entry as it appears in the value of an ``identifiers``
    map key in upstream ``index.json``. The map's key (the reverse-DNS
    identifier like ``com.github.autopkg.download.Firefox``) is passed
    separately when ingesting; it is not part of the entry value.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    repo: str
    path: str
    parent: str | None = None
    shortname: str
    inferred_type: str | None = None
    children: list[str] = []
