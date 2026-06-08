"""Tests for the Jamf App Installers titles API fetch (auth + pagination), mocked."""

import httpx
import pytest
from patcher_api.ingest.jamf import (
    fetch_jai_catalog,
    fetch_jai_titles,
    ingest_jai_titles,
)
from patcher_api.models.jamf import JamfAppInstaller
from patcher_api.schemas.jamf import JaiTitle
from sqlalchemy import select

_BASE = "https://dummy.jamfcloud.com"


def _title(tid: str, bundle: str, name: str) -> dict:
    return {"id": tid, "bundleId": bundle, "titleName": name, "version": "1.0"}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_authenticates_then_returns_titles():
    seen = {"token_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth/token":
            seen["token_calls"] += 1
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 60})
        if request.url.path == "/api/v1/app-installers/titles":
            assert request.headers["Authorization"] == "Bearer tok123"
            return httpx.Response(
                200,
                json={
                    "totalCount": 2,
                    "results": [
                        _title("001", "com.adobe.acc", "Adobe Creative Cloud"),
                        _title("029", "com.adobe.Acrobat.Pro", "Adobe Acrobat"),
                    ],
                },
            )
        return httpx.Response(404)

    titles = await fetch_jai_titles(_BASE, "cid", "secret", client=_client(handler))

    assert seen["token_calls"] == 1  # one auth for the whole sweep
    assert [t.id for t in titles] == ["001", "029"]
    assert titles[0].bundle_id == "com.adobe.acc"  # the stitch key landed
    assert titles[0].version == "1.0"


@pytest.mark.asyncio
async def test_paginates_until_total_count_reached():
    pages = {
        0: {"totalCount": 3, "results": [_title("001", "a", "A"), _title("002", "b", "B")]},
        1: {"totalCount": 3, "results": [_title("003", "c", "C")]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        page = int(request.url.params["page"])
        return httpx.Response(200, json=pages[page])

    titles = await fetch_jai_titles(_BASE, "cid", "secret", client=_client(handler))
    assert [t.id for t in titles] == ["001", "002", "003"]


@pytest.mark.asyncio
async def test_stops_on_empty_page_without_infinite_loop():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        # totalCount overstates reality; an empty results page must end the loop.
        return httpx.Response(200, json={"totalCount": 999, "results": []})

    titles = await fetch_jai_titles(_BASE, "cid", "secret", client=_client(handler))
    assert titles == []


def _detail(tid: str, bundle: str, name: str) -> dict:
    return {
        "id": tid,
        "bundleId": bundle,
        "titleName": name,
        "version": "1.0",
        "architecture": "universal",
        "mediaSourceType": "EXTERNAL_URL",
        "originalMediaSources": [{"url": f"https://vendor.example/{tid}.pkg", "hashType": "MD5"}],
    }


@pytest.mark.asyncio
async def test_catalog_enriches_each_title_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        if path == "/api/v1/app-installers/titles":
            return httpx.Response(
                200,
                json={
                    "totalCount": 2,
                    "results": [
                        _title("001", "a", "A"),
                        _title("002", "b", "B"),
                    ],
                },
            )
        tid = path.rsplit("/", 1)[-1]  # detail call
        return httpx.Response(200, json=_detail(tid, f"com.x.{tid}", f"Name {tid}"))

    titles = await fetch_jai_catalog(_BASE, "cid", "secret", client=_client(handler))
    assert len(titles) == 2
    # The detail fields (absent from the list shape) are now populated.
    assert titles[0].architecture == "universal"
    assert titles[0].media_sources[0].url == "https://vendor.example/001.pkg"


@pytest.mark.asyncio
async def test_catalog_falls_back_to_lean_record_on_detail_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/oauth/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        if path == "/api/v1/app-installers/titles":
            return httpx.Response(
                200, json={"totalCount": 1, "results": [_title("001", "com.x", "X")]}
            )
        return httpx.Response(500)  # detail blows up

    titles = await fetch_jai_catalog(_BASE, "cid", "secret", client=_client(handler))
    assert len(titles) == 1
    assert titles[0].bundle_id == "com.x"  # lean record preserved, run didn't abort
    assert titles[0].media_sources == []  # detail never landed


@pytest.mark.asyncio
async def test_ingest_persists_titles_with_derived_source_and_host(test_session):
    titles = [
        JaiTitle(
            id="029",
            bundle_id="com.adobe.Acrobat.Pro",
            title_name="Adobe Acrobat DC Continuous",
            version="26.001",
            architecture="universal",
            media_source_type="EXTERNAL_URL",
            media_sources=[{"url": "https://ardownload3.adobe.com/x.pkg"}],
        ),
        JaiTitle(
            id="001",
            bundle_id="com.adobe.acc",
            title_name="Adobe Creative Cloud",
            version="6.9",
            media_source_type="JAMF_SERVER",
            media_sources=[{"url": "https://ccmdls.adobe.com/y.dmg"}],
        ),
    ]
    ingested, skipped = await ingest_jai_titles(test_session, titles)
    assert (ingested, skipped) == (2, 0)

    rows = {r.title: r for r in (await test_session.scalars(select(JamfAppInstaller))).all()}
    acro = rows["Adobe Acrobat DC Continuous"]
    assert acro.source == "External"  # EXTERNAL_URL -> External
    assert acro.host == "ardownload3.adobe.com"  # derived from the media URL
    assert acro.bundle_id == "com.adobe.Acrobat.Pro"
    assert acro.jamf_id == "029"
    assert acro.download_url == "https://ardownload3.adobe.com/x.pkg"

    cc = rows["Adobe Creative Cloud"]
    assert cc.source == "Jamf"  # JAMF_SERVER -> Jamf, no external host
    assert cc.host is None
