"""
Tests for :class:`patcher.PatcherAPIClient`.

Uses ``httpx.MockTransport`` to stub the API — no real network, no recorded
cassettes. The transport is injected by patching the client's lazy ``http``
property so we cover both the request-construction path (URL composition,
query params, POST body absence) and response-parsing (200 / 404 / 422 /
non-JSON body).
"""

from __future__ import annotations

import httpx
import pytest
from src.patcher import PatcherAPIClient
from src.patcher.clients.patcher_api import (
    App,
    AppSources,
    DriftEntry,
    DriftResponse,
    GeneratedLabel,
    InstallMethod,
)
from src.patcher.core.exceptions import APIResponseError

_FIREFOX_RECORD = {
    "slug": "firefox",
    "bundle_id": "org.mozilla.firefox",
    "name": "Firefox",
    "vendor": "Mozilla",
    "current_version": "150.0.3",
    "latest_release_date": None,
    "download_url": "https://download.mozilla.org/firefox.pkg",
    "install_method": "pkg",
    "sha256": None,
    "sources": ["installomator", "homebrew_cask"],
}


def _build_client(handler) -> PatcherAPIClient:
    """Construct a client whose lazy httpx client uses the given mock handler."""
    client = PatcherAPIClient(base_url="https://test.patcherctl.dev")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_list_apps_returns_parsed_records():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_FIREFOX_RECORD])

    client = _build_client(handler)
    try:
        apps = await client.list_apps()
    finally:
        await client.aclose()

    assert len(apps) == 1
    assert isinstance(apps[0], App)
    assert apps[0].slug == "firefox"
    assert apps[0].install_method == InstallMethod.PKG
    assert str(apps[0].download_url) == "https://download.mozilla.org/firefox.pkg"
    assert str(requests[0].url) == "https://test.patcherctl.dev/apps?limit=100&offset=0"


@pytest.mark.asyncio
async def test_list_apps_forwards_filter_params():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    client = _build_client(handler)
    try:
        await client.list_apps(
            vendor="Mozilla",
            source="installomator",
            exclude_source="autopkg",
            limit=25,
            offset=50,
        )
    finally:
        await client.aclose()

    assert seen == {
        "vendor": "Mozilla",
        "source": "installomator",
        "exclude_source": "autopkg",
        "limit": "25",
        "offset": "50",
    }


@pytest.mark.asyncio
async def test_get_app_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "App with slug 'nope' not found"})

    client = _build_client(handler)
    try:
        result = await client.get_app("nope")
    finally:
        await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_get_app_returns_record():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_FIREFOX_RECORD)

    client = _build_client(handler)
    try:
        result = await client.get_app("firefox")
    finally:
        await client.aclose()

    assert isinstance(result, App)
    assert result.vendor == "Mozilla"


@pytest.mark.asyncio
async def test_get_app_sources_returns_parsed_sources():
    payload = {
        "installomator": {
            "label_name": "firefoxpkg",
            "label_url": "https://example.com/firefoxpkg.sh",
            "raw": {"name": "Firefox", "type": "pkg"},
        },
        "homebrew_cask": None,
        "autopkg": None,
        "mas": None,
        "jamf_app_installer": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        result = await client.get_app_sources("firefox")
    finally:
        await client.aclose()

    assert isinstance(result, AppSources)
    assert result.installomator is not None
    assert result.installomator.label_name == "firefoxpkg"
    assert result.homebrew_cask is None


@pytest.mark.asyncio
async def test_generate_label_returns_parsed_response():
    payload = {
        "label_name": "firefox",
        "content": {"name": "Mozilla Firefox", "type": "pkg"},
        "sources_used": ["installomator", "homebrew_cask"],
        "warnings": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        result = await client.generate_label("firefox")
    finally:
        await client.aclose()

    assert isinstance(result, GeneratedLabel)
    assert result.label_name == "firefox"
    assert "installomator" in result.sources_used


@pytest.mark.asyncio
async def test_non_404_error_raises_api_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "App has no source detail"})

    client = _build_client(handler)
    try:
        with pytest.raises(APIResponseError):
            await client.generate_label("firefox")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_async_context_manager_closes_pool():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with PatcherAPIClient(base_url="https://test.patcherctl.dev") as client:
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.list_apps()
    # After exiting the async with, the pool was released. Re-accessing
    # `http` would lazy-construct a fresh client.
    assert client._http_client is None


@pytest.mark.asyncio
async def test_list_apps_rejects_non_array_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        # Wrong shape: API returns dict instead of list. Client should reject.
        return httpx.Response(200, json={"detail": "shouldn't be here"})

    client = _build_client(handler)
    try:
        with pytest.raises(APIResponseError, match="JSON array"):
            await client.list_apps()
    finally:
        await client.aclose()


_DRIFT_ENTRY = {
    "slug": "slack",
    "name": "Slack",
    "vendor": "Slack",
    "versions": [
        {"source": "installomator", "version": "4.32.0", "parsed_ok": True},
        {"source": "homebrew_cask", "version": "4.40.0", "parsed_ok": True},
    ],
    "leader": "homebrew_cask",
    "laggard": "installomator",
}


@pytest.mark.asyncio
async def test_list_drift_returns_parsed_response():
    payload = {
        "total_scanned": 5,
        "total_with_drift": 1,
        "entries": [_DRIFT_ENTRY],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        result = await client.list_drift()
    finally:
        await client.aclose()

    assert isinstance(result, DriftResponse)
    assert result.total_scanned == 5
    assert result.total_with_drift == 1
    assert len(result.entries) == 1
    assert result.entries[0].slug == "slack"
    assert result.entries[0].leader == "homebrew_cask"


@pytest.mark.asyncio
async def test_list_drift_forwards_filter_params():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"total_scanned": 0, "total_with_drift": 0, "entries": []})

    client = _build_client(handler)
    try:
        await client.list_drift(
            vendor="Slack",
            source="installomator",
            limit=10,
            offset=5,
        )
    finally:
        await client.aclose()

    assert seen == {
        "vendor": "Slack",
        "source": "installomator",
        "limit": "10",
        "offset": "5",
    }


@pytest.mark.asyncio
async def test_list_drift_hits_drift_path_not_slug():
    """``/apps/drift`` must not collide with ``/apps/{slug}``."""
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"total_scanned": 0, "total_with_drift": 0, "entries": []})

    client = _build_client(handler)
    try:
        await client.list_drift()
    finally:
        await client.aclose()

    assert seen_paths == ["/apps/drift"]


@pytest.mark.asyncio
async def test_get_app_drift_returns_parsed_entry():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_DRIFT_ENTRY)

    client = _build_client(handler)
    try:
        result = await client.get_app_drift("slack")
    finally:
        await client.aclose()

    assert isinstance(result, DriftEntry)
    assert result.slug == "slack"
    assert {v.source for v in result.versions} == {"installomator", "homebrew_cask"}


@pytest.mark.asyncio
async def test_get_app_drift_returns_none_for_null_body():
    """Server signals "exists but no drift" with a 200 + ``null`` body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"null",
            headers={"content-type": "application/json"},
        )

    client = _build_client(handler)
    try:
        result = await client.get_app_drift("firefox")
    finally:
        await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_get_app_drift_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "App with slug 'nope' not found"})

    client = _build_client(handler)
    try:
        result = await client.get_app_drift("nope")
    finally:
        await client.aclose()

    assert result is None


@pytest.mark.asyncio
async def test_get_app_drift_raises_on_non_404_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _build_client(handler)
    try:
        with pytest.raises(APIResponseError):
            await client.get_app_drift("firefox")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_base_url_trailing_slash_is_normalized():
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[])

    client = PatcherAPIClient(base_url="https://test.patcherctl.dev/")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await client.list_apps()
    finally:
        await client.aclose()

    # No double slash from the trailing-slash base + path concatenation.
    assert seen_urls[0].startswith("https://test.patcherctl.dev/apps?")


@pytest.mark.asyncio
async def test_get_jamf_index_returns_code_to_slug_map():
    payload = {"0B3": ["firefox", "firefoxpkg"], "0F9": ["zoom"]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/apps/jamf-index"
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        result = await client.get_jamf_index()
    finally:
        await client.aclose()

    assert result == {"0B3": ["firefox", "firefoxpkg"], "0F9": ["zoom"]}
