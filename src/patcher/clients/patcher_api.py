"""
Client for the Patcher API (https://api.patcherctl.dev).

The Patcher API serves a community catalog of macOS app patching metadata
stitched from Installomator, Homebrew Cask, AutoPkg, MAS, and the Jamf App
Installers index. This client wraps the four ``/apps*`` read endpoints
plus the ``POST /apps/{slug}/generate-label`` label-generator.

Read endpoints are public — no authentication required. The client is
useful standalone (enrich your own scripts with stitched catalog data)
and is also the backend :class:`PatcherClient` uses internally for
Installomator-style matching once the package adopts API-sourced labels.

Pydantic response models defined here mirror the API's wire format but
are intentionally decoupled from the ``patcher-api`` workspace package —
the wire format is the contract, not a Python import.

Usage::

    from patcher import PatcherAPIClient

    async with PatcherAPIClient() as client:
        apps = await client.list_apps(vendor="Mozilla")
        firefox = await client.get_app("firefox")
        if firefox is not None:
            print(firefox.current_version, firefox.download_url)
"""

from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from ..core.exceptions import APIResponseError
from . import HTTPClient

DEFAULT_BASE_URL = "https://api.patcherctl.dev"


class InstallMethod(StrEnum):
    """Mirrors Installomator's ``type`` variable."""

    DMG = "dmg"
    PKG = "pkg"
    ZIP = "zip"
    TBZ = "tbz"
    PKG_IN_DMG = "pkgInDmg"
    PKG_IN_ZIP = "pkgInZip"
    APP_IN_DMG_IN_ZIP = "appInDmgInZip"


class App(BaseModel):
    """A stitched catalog record. One row per app slug."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    bundle_id: str | None = None
    name: str
    vendor: str | None = None
    current_version: str | None = None
    latest_release_date: date | None = None
    download_url: HttpUrl | None = None
    install_method: InstallMethod | None = None
    sha256: str | None = None
    sources: list[str]
    cves: list[str] = []


class InstallomatorSource(BaseModel):
    label_name: str
    label_url: HttpUrl
    raw: dict[str, Any]


class HomebrewCaskSource(BaseModel):
    token: str
    cask_json: dict[str, Any]


class AutopkgRecipeEntry(BaseModel):
    identifier: str
    name: str
    shortname: str
    repo: str
    path: str
    parent_identifier: str | None = None
    inferred_type: str | None = None
    recipe_url: HttpUrl | None = None


class AutopkgSource(BaseModel):
    recipes: list[AutopkgRecipeEntry]


class MasSource(BaseModel):
    bundle_id: str
    store_url: HttpUrl | None = None
    raw: dict[str, Any]


class JamfAppInstallerSource(BaseModel):
    title: str
    source: str
    host: str | None = None


class AppSources(BaseModel):
    """Per-source payloads for a single app slug. Source values are ``None`` when that source didn't contribute."""

    model_config = ConfigDict(extra="ignore")

    installomator: InstallomatorSource | None = None
    homebrew_cask: HomebrewCaskSource | None = None
    autopkg: AutopkgSource | None = None
    mas: MasSource | None = None
    jamf_app_installer: JamfAppInstallerSource | None = None


class GeneratedLabel(BaseModel):
    """Response from ``POST /apps/{slug}/generate-label``."""

    model_config = ConfigDict(extra="ignore")

    label_name: str
    content: dict[str, Any]
    sources_used: list[str]
    warnings: list[str]


class PatcherAPIClient(HTTPClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        max_concurrency: int = 5,
    ) -> None:
        """
        Construct a :class:`PatcherAPIClient` pointed at a Patcher API instance.

        :param base_url: The API root. Defaults to the public instance
            at ``https://api.patcherctl.dev``. Override for self-hosted
            deployments or local development against ``make serve-api``.
        :type base_url: str
        :param max_concurrency: Max concurrent in-flight requests. The API
            is cached behind Cloudflare with per-deploy ETags, so even
            modest concurrency rarely hits origin.
        :type max_concurrency: int
        """
        super().__init__(max_concurrency=max_concurrency)
        self.base_url = base_url.rstrip("/")

    async def __aenter__(self) -> PatcherAPIClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def list_apps(
        self,
        *,
        vendor: str | None = None,
        source: str | None = None,
        exclude_source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[App]:
        """
        ``GET /apps`` — list catalog apps with optional filters and pagination.

        :param vendor: Case-insensitive exact vendor match. None disables.
        :param source: Include only apps whose ``sources`` array contains
            this token (``installomator``, ``homebrew_cask``, ``autopkg``,
            ``mas``, ``jamf_app_installer``).
        :param exclude_source: Drop apps whose ``sources`` array contains
            this token.
        :param limit: Maximum rows to return. Server caps at 1000.
        :param offset: Number of filtered rows to skip.
        :return: Catalog records, ordered by slug for deterministic paging.
        :raises APIResponseError: Network failure, non-2xx response, or
            unparseable body.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if vendor is not None:
            params["vendor"] = vendor
        if source is not None:
            params["source"] = source
        if exclude_source is not None:
            params["exclude_source"] = exclude_source

        payload = await self._get("/apps", params=params)
        if not isinstance(payload, list):
            raise APIResponseError(
                "Unexpected response shape from /apps (expected a JSON array)",
                url=f"{self.base_url}/apps",
            )
        return [App.model_validate(row) for row in payload]

    async def get_app(self, slug: str) -> App | None:
        """
        ``GET /apps/{slug}`` — fetch one app by slug. Returns ``None`` on 404.

        :param slug: URL-friendly app identifier (e.g. ``"firefox"``).
        :return: The catalog record, or ``None`` if the slug isn't in the catalog.
        :raises APIResponseError: For any non-2xx status other than 404.
        """
        try:
            payload = await self._get(f"/apps/{slug}")
        except APIResponseError as exc:
            if getattr(exc, "not_found", False):
                return None
            raise
        return App.model_validate(payload)

    async def get_app_sources(self, slug: str) -> AppSources | None:
        """
        ``GET /apps/{slug}/sources`` — fetch per-source payloads for a slug.

        Returns ``None`` on 404. Source values inside the returned
        :class:`~patcher.clients.patcher_api.AppSources` object are ``None`` for sources that didn't
        contribute data for this slug.
        """
        try:
            payload = await self._get(f"/apps/{slug}/sources")
        except APIResponseError as exc:
            if getattr(exc, "not_found", False):
                return None
            raise
        return AppSources.model_validate(payload)

    async def generate_label(self, slug: str) -> GeneratedLabel | None:
        """
        ``POST /apps/{slug}/generate-label`` — server-side label projection.

        Returns ``None`` on 404. The returned :class:`~patcher.clients.patcher_api.GeneratedLabel` carries
        a ``warnings`` array surfacing fields that couldn't be resolved
        (most commonly ``expectedTeamID`` for Cask-only apps).
        """
        try:
            payload = await self._post(f"/apps/{slug}/generate-label")
        except APIResponseError as exc:
            if getattr(exc, "not_found", False):
                return None
            raise
        return GeneratedLabel.model_validate(payload)

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with self.semaphore:
                response = await self.http.get(url, params=params)
        except httpx.RequestError as exc:
            raise APIResponseError(
                "Network error contacting Patcher API",
                url=url,
                error_msg=str(exc),
            )
        return self._parse(response, url)

    async def _post(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with self.semaphore:
                response = await self.http.post(url)
        except httpx.RequestError as exc:
            raise APIResponseError(
                "Network error contacting Patcher API",
                url=url,
                error_msg=str(exc),
            )
        return self._parse(response, url)

    @staticmethod
    def _parse(response: httpx.Response, url: str) -> Any:
        if response.status_code == 404:
            raise APIResponseError(
                "Requested resource was not found.",
                url=url,
                status_code=response.status_code,
                not_found=True,
            )
        if not response.is_success:
            try:
                detail = response.json().get("detail")
            except (ValueError, json.JSONDecodeError):
                detail = None
            raise APIResponseError(
                "Non-success HTTP status from Patcher API",
                url=url,
                status_code=response.status_code,
                error=detail or "(no detail in response body)",
            )
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise APIResponseError(
                "Failed parsing JSON from Patcher API response",
                url=url,
                status_code=response.status_code,
                error_msg=str(exc),
            )


__all__ = [
    "App",
    "AppSources",
    "AutopkgRecipeEntry",
    "AutopkgSource",
    "DEFAULT_BASE_URL",
    "GeneratedLabel",
    "HomebrewCaskSource",
    "InstallMethod",
    "InstallomatorSource",
    "JamfAppInstallerSource",
    "MasSource",
    "PatcherAPIClient",
]
