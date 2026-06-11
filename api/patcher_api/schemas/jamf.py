"""
Pydantic schemas for Jamf title catalogs.

:class:`JaiTitle` / :class:`JaiTitlePage` mirror Jamf Pro's *App Installers
titles* API (``GET /api/v1/app-installers/titles``): ``bundle_id`` (the exact
stitch key), ``version``, per-arch download sources, and the Jamf title ``id``.
:class:`JamfTitle` mirrors the broader Classic API ``patchavailabletitles``
feed — every Patch Management title, keyed by ``name_id``. The title endpoints
are catalog-global, so they return the same data on any instance.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from patcher_api.schemas.base import BaseModel, UpstreamModel


class JaiMediaSource(UpstreamModel):
    """One download source for a title — titles often carry one per architecture."""

    url: str
    hash: str | None = None
    hash_type: str | None = None


class JaiTitle(UpstreamModel):
    """
    A Jamf App Installers catalog title.

    The list endpoint returns the leading identity fields; the per-title detail
    endpoint adds the rest. Everything past ``title_name`` is optional, so the
    same model parses both shapes. Aliases are auto-generated camelCase except
    the two ``original*`` fields, whose wire names don't follow from the
    snake_case field name.
    """

    id: str  # Jamf title identifier; string (zero-padded numeric on the dummy, alphanumeric on prod)
    bundle_id: str | None = None  # exact stitch key
    title_name: str
    publisher: str | None = None
    icon_url: str | None = None
    version: str | None = None
    short_version: str | None = None
    architecture: str | None = None  # universal / arm64 / x86_64
    minimum_os_version: str | None = None
    language: str | None = None
    availability_date: datetime | None = None
    media_source_type: str | None = None  # EXTERNAL_URL / JAMF_SERVER
    media_sources: list[JaiMediaSource] = Field(default_factory=list, alias="originalMediaSources")
    size_in_bytes: int | None = None
    installation_path_shared: bool | None = None
    package_signing_identity: str | None = None
    installer_package_hash: str | None = None
    installer_package_hash_type: str | None = None
    # Keep install-mechanics signals (e.g. suppress_auto_update flags self-updating apps Patcher needn't chase).
    launch_daemon_included: bool | None = None
    notification_available: bool | None = None
    suppress_auto_update: bool | None = None
    terms_and_conditions: list[Any] = Field(
        default_factory=list, alias="originalTermsAndConditions"
    )


class JaiTitlePage(UpstreamModel):
    """One page of ``GET /api/v1/app-installers/titles`` (``totalCount`` + ``results``)."""

    total_count: int
    results: list[JaiTitle]


class JamfTitle(BaseModel):
    """
    One parsed ``patchavailabletitles`` entry (``name_id``, publisher, current
    version, last-modified, app name).

    .. versionadded:: 3.3.0
    """

    name_id: str
    publisher: str
    current_version: str
    last_modified: datetime
    app_name: str
