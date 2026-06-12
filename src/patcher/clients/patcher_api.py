"""
Client for the Patcher API (https://api.patcherctl.dev).

The Patcher API serves a community catalog of macOS app patching metadata
stitched from Installomator, Homebrew Cask, AutoPkg, and the Jamf App
Installers index. This client wraps the four ``/apps*`` read endpoints
plus the ``POST /apps/{slug}/generate-label`` label-generator.

Read endpoints are public — no authentication required. The client is
useful standalone (enrich your own scripts with stitched catalog data)
and is also the backend :class:`PatcherClient` uses internally for
Installomator-style matching once the package adopts API-sourced labels.

Response models are imported from :mod:`patcher.catalog.schemas`, the single
source of truth shared with the ``patcher-api`` server, so the client can
never drift from what the server serializes. They are re-exported here for
backwards compatibility with ``from patcher.clients.patcher_api import App``.

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
import os
from typing import Any

import httpx

from ..catalog import (
    App,
    AppSources,
    AutopkgRecipeEntry,
    AutopkgSource,
    DriftEntry,
    DriftResponse,
    GeneratedLabel,
    HomebrewCaskSource,
    InstallMethod,
    InstallomatorSource,
    JamfAppInstallerSource,
    SourceVersion,
)
from ..core.exceptions import APIResponseError
from . import HTTPClient

# allow env var override for local testing
DEFAULT_BASE_URL = os.environ.get("PATCHER_API_URL", "https://api.patcherctl.dev")

__all__ = [
    "App",
    "AppSources",
    "AutopkgRecipeEntry",
    "AutopkgSource",
    "DriftEntry",
    "DriftResponse",
    "GeneratedLabel",
    "HomebrewCaskSource",
    "InstallMethod",
    "InstallomatorSource",
    "JamfAppInstallerSource",
    "SourceVersion",
    "PatcherAPIClient",
    "DEFAULT_BASE_URL",
]


class PatcherAPIClient(HTTPClient):
    """Read client for the Patcher catalog API (app lookups, sources, drift, the jamf-index)."""

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
            ``jamf_app_installer``).
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
        :class:`~patcher.catalog.schemas.AppSources` object are ``None`` for sources that didn't
        contribute data for this slug.
        """
        try:
            payload = await self._get(f"/apps/{slug}/sources")
        except APIResponseError as exc:
            if getattr(exc, "not_found", False):
                return None
            raise
        return AppSources.model_validate(payload)

    async def list_drift(
        self,
        *,
        vendor: str | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> DriftResponse:
        """
        ``GET /apps/drift`` — scan the catalog for cross-source version drift.

        Iterates apps with at least two versioned sources (Installomator
        and Homebrew Cask, today) and returns those whose sources
        disagree on what "latest" means. A vendor or source filter
        narrows the result; pagination operates on the filtered count.

        :param vendor: Case-insensitive exact vendor match. None disables.
        :param source: Drop entries where this source did not participate
            in the disagreement (``installomator`` or ``homebrew_cask``).
        :param limit: Maximum entries on this page. Server caps at 1000.
        :param offset: Entries to skip before the page.
        :return: Drift entries plus aggregate counts.
        :raises APIResponseError: Network failure, non-2xx response, or
            unparseable body.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if vendor is not None:
            params["vendor"] = vendor
        if source is not None:
            params["source"] = source

        payload = await self._get("/apps/drift", params=params)
        return DriftResponse.model_validate(payload)

    async def get_jamf_index(self) -> dict[str, list[str]]:
        """
        ``GET /apps/jamf-index`` — the Jamf softwareTitleNameId → slug index.

        Maps each Jamf App Installer title code (e.g. ``"0B3"``) to the
        catalog slugs that carry it. Used for deterministic, exact-code
        matching of a customer's patch titles before any fuzzy fallback.

        :return: Mapping of title code to the list of catalog slugs.
        :raises APIResponseError: Network failure, non-2xx response, or
            unparseable body.
        """
        return await self._get("/apps/jamf-index")

    async def get_app_drift(self, slug: str) -> DriftEntry | None:
        """
        ``GET /apps/{slug}/drift`` — drift detection for a single app.

        Returns ``None`` in two cases: the slug isn't in the catalog
        (404), or the app exists but has no drift (200 with ``null``
        body — either fewer than two versioned sources, or every source
        agrees). Callers that need to distinguish should call
        :meth:`get_app` first to confirm existence.

        :param slug: URL-friendly app identifier.
        :return: A drift entry, or ``None`` for "no drift to report."
        :raises APIResponseError: For any non-2xx status other than 404.
        """
        try:
            payload = await self._get(f"/apps/{slug}/drift")
        except APIResponseError as exc:
            if getattr(exc, "not_found", False):
                return None
            raise
        if payload is None:
            return None
        return DriftEntry.model_validate(payload)

    async def generate_label(self, slug: str) -> GeneratedLabel | None:
        """
        ``POST /apps/{slug}/generate-label`` — server-side label projection.

        Returns ``None`` on 404. The returned :class:`~patcher.catalog.schemas.GeneratedLabel` carries
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
        response = await self._request("GET", url, params=params)
        return self._parse(response, url)

    async def _post(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        response = await self._request("POST", url)
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

        return response.json()
