"""
Catalog wire schemas — the single source of truth for the Patcher API contract.

These Pydantic models are the shape of the ``/apps*`` responses, shared by both
sides of the wire: the ``patcher-api`` server uses them as FastAPI
``response_model``s, and :class:`~patcher.clients.patcher_api.PatcherAPIClient`
parses responses into them. One definition means the client can never drift
from what the server serializes.

The shared config is ``from_attributes=True`` (so the server can serialize ORM
rows) plus ``extra="ignore"`` (so the client tolerates fields a newer server adds).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, HttpUrl


class _CatalogSchema(BaseModel):
    """Shared config: serialize from ORM attributes; ignore unknown wire fields."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class InstallMethod(StrEnum):
    """Mirrors Installomator's ``type`` variable."""

    DMG = "dmg"
    PKG = "pkg"
    ZIP = "zip"
    TBZ = "tbz"
    PKG_IN_DMG = "pkgInDmg"
    PKG_IN_ZIP = "pkgInZip"
    APP_IN_DMG_IN_ZIP = "appInDmgInZip"


class App(_CatalogSchema):
    """A stitched catalog record. One row per app slug; returned by ``/apps`` and ``/apps/{slug}``."""

    slug: str
    bundle_id: str | None = None
    name: str
    vendor: str | None = None
    current_version: str | None = None
    latest_release_date: date | None = None
    download_url: HttpUrl | None = None
    install_method: InstallMethod | None = None
    expected_team_id: str | None = None
    sha256: str | None = None
    sources: list[str]


class InstallomatorSource(_CatalogSchema):
    """Installomator source detail: label name, fragment URL, and the raw parsed fields."""

    label_name: str
    label_url: HttpUrl
    raw: dict[str, Any]


class HomebrewCaskSource(_CatalogSchema):
    """Homebrew Cask source detail: the cask token and its raw JSON."""

    token: str
    cask_json: dict[str, Any]


class AutopkgRecipeEntry(_CatalogSchema):
    """
    A single AutoPkg recipe attached to an app.

    ``name``/``shortname`` are optional: shared-processor recipes carry
    ``name: null`` and some recipes have no clean shortname.
    """

    identifier: str
    name: str | None = None
    shortname: str | None = None
    repo: str
    path: str
    parent_identifier: str | None = None
    inferred_type: str | None = None
    recipe_url: HttpUrl | None = None


class AutopkgSource(_CatalogSchema):
    """All AutoPkg recipes matched to an app (multi-recipe by nature)."""

    recipes: list[AutopkgRecipeEntry]


class JamfAppInstallerSource(_CatalogSchema):
    """
    Jamf App Installers coverage for an app.

    ``title``/``source``/``host`` come from the public HTML catalog; the rest is
    enrichment from the App Installers titles API (absent on HTML-only rows).
    """

    title: str
    source: str
    host: str | None = None
    bundle_id: str | None = None
    version: str | None = None
    jamf_id: str | None = None
    download_url: str | None = None
    architecture: str | None = None


class AppSources(_CatalogSchema):
    """Per-source detail payloads for one app slug; each is ``None`` when that source didn't contribute."""

    installomator: InstallomatorSource | None = None
    homebrew_cask: HomebrewCaskSource | None = None
    autopkg: AutopkgSource | None = None
    jamf_app_installer: JamfAppInstallerSource | None = None


class GeneratedLabel(_CatalogSchema):
    """Response from ``POST /apps/{slug}/generate-label``: structured label fields plus any warnings."""

    label_name: str
    content: dict[str, Any]
    sources_used: list[str]
    warnings: list[str]


class SourceVersion(_CatalogSchema):
    """One source's reported version for an app."""

    source: str
    version: str
    parsed_ok: bool


class DriftEntry(_CatalogSchema):
    """
    Drift detected on a single app.

    ``leader``/``laggard`` are the highest/lowest parsed-version sources; both
    are ``None`` when a version string couldn't be parsed (e.g. Cask date-style
    versions), in which case ``versions`` is still complete.
    """

    slug: str
    name: str
    vendor: str | None = None
    versions: list[SourceVersion]
    leader: str | None = None
    laggard: str | None = None


class DriftResponse(_CatalogSchema):
    """
    Paginated drift results from ``GET /apps/drift``.

    ``total_scanned`` counts apps with two or more versioned sources;
    ``total_with_drift`` is the unpaged count of disagreements matching the
    request's filters.
    """

    total_scanned: int
    total_with_drift: int
    entries: list[DriftEntry]
