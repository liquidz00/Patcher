"""
Cross-source version drift detection schemas.

Drift answers a question Patcher's stitched catalog is uniquely positioned to
answer: *do upstream sources agree on what "latest" means for this app?* When
they don't, one source is probably silently stuck — the vendor moved their
release artifact, the label still finds the old location, and the tool keeps
reporting the old version as latest indefinitely.

Only sources that expose a stable per-app version string participate: today
that's Installomator (``appNewVersion``) and Homebrew Cask
(``cask_json['version']``). AutoPkg recipes resolve at run time so they
don't carry a static latest version. Jamf App Installers is a coverage
indicator only. Mac App Store's overlap with the version-bearing sources is
empirically negligible (see ``project_patcher_mas_low_value.md``).
"""

from pydantic import BaseModel


class SourceVersion(BaseModel):
    """One source's reported version for an app."""

    source: str
    version: str
    parsed_ok: bool


class DriftEntry(BaseModel):
    """
    Drift detected on a single app.

    ``leader`` and ``laggard`` are the source names with the highest and
    lowest parsed versions; both are ``None`` when at least one version
    string couldn't be parsed (e.g. Cask's ``2025-04-15`` date-style
    versions). In that case ``versions`` is still complete and consumers
    can render the disagreement without ordering it.
    """

    slug: str
    name: str
    vendor: str | None = None
    versions: list[SourceVersion]
    leader: str | None = None
    laggard: str | None = None


class DriftResponse(BaseModel):
    """
    Paginated drift results across the catalog.

    ``total_scanned`` is the number of apps inspected (those with ≥2
    versioned sources); ``total_with_drift`` is the subset where the
    sources disagreed. ``entries`` is the page of disagreements.
    """

    total_scanned: int
    total_with_drift: int
    entries: list[DriftEntry]
