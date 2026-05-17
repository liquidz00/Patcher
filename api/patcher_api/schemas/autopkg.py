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

    ``name`` and ``shortname`` are intentionally optional because the
    upstream index has substantial inconsistency on these fields. Shared-
    processor utility recipes typically have ``name: null``; some app
    recipes have unusual ``shortname`` values (often containing special
    characters like ``.`` or whitespace) that the index doesn't capture
    cleanly. Preserving these rows keeps the catalog complete; the stitch
    matching logic already gates on a non-empty normalized name, so
    recipes without one naturally never attach to apps.
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    description: str | None = None
    repo: str
    path: str
    parent: str | None = None
    shortname: str | None = None
    inferred_type: str | None = None
    children: list[str] = []
