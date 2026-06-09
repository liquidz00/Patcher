"""
Tests for the Jamf patch-title catalog: the Classic API XML fetch, the upsert
ingest, and the expanded ``/apps/jamf-index`` coverage.

The captured Classic API responses live in ``fixtures/available_titles.{xml,json}``
(a representative slice of the real ``patchavailabletitles`` payload).
"""

import json
from pathlib import Path

import httpx
import pytest
from patcher_api.ingest.jamf import fetch_catalog, ingest_jamf_catalog
from patcher_api.models.app import App
from patcher_api.models.jamf import JamfCatalogTitle
from patcher_api.schemas.jamf import JamfTitle
from sqlalchemy import select

FIXTURES = Path(__file__).parent / "fixtures"
_BASE = "https://dummy.jamfcloud.com"
_TITLES_PATH = "/JSSResource/patchavailabletitles/sourceid/1"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_catalog_parses_available_titles_xml():
    xml_bytes = (FIXTURES / "available_titles.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/oauth/token":
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})
        if request.url.path == _TITLES_PATH:
            assert request.headers["Accept"] == "application/xml"
            assert request.headers["Authorization"] == "Bearer tok"
            return httpx.Response(200, content=xml_bytes)
        return httpx.Response(404)

    titles = await fetch_catalog(_BASE, "cid", "secret", client=_client(handler))

    assert [t.name_id for t in titles] == ["518", "575", "0F5", "0F6", "0F7", "0F8"]
    first = titles[0]
    assert first.app_name == "010 Editor"
    assert first.publisher == "SweetScape"
    assert first.current_version == "16.0.4"
    # the trailing-Z timestamp parsed into a tz-aware datetime
    assert first.last_modified.year == 2026
    assert first.last_modified.tzinfo is not None


@pytest.mark.asyncio
async def test_ingest_jamf_catalog_upserts_and_is_idempotent(test_session):
    data = json.loads((FIXTURES / "available_titles.json").read_text())
    titles = [JamfTitle.model_validate(d) for d in data]

    ingested, skipped = await ingest_jamf_catalog(test_session, titles)
    assert (ingested, skipped) == (6, 0)

    rows = {r.name_id: r for r in (await test_session.scalars(select(JamfCatalogTitle))).all()}
    assert len(rows) == 6
    assert rows["518"].app_name == "010 Editor"
    assert rows["0F8"].publisher == "AgileBits"
    assert rows["518"].last_modified.year == 2026  # value round-tripped through the JSON column

    # Re-ingesting the same catalog updates in place — no duplicate rows.
    await ingest_jamf_catalog(test_session, titles)
    count = len((await test_session.scalars(select(JamfCatalogTitle))).all())
    assert count == 6


@pytest.mark.asyncio
async def test_jamf_index_unions_name_matched_titles(client, test_session):
    """A jamf_titles entry maps its name_id to a catalog slug via normalized name."""
    test_session.add(App(slug="my-editor", name="010 Editor", sources=["installomator"]))
    test_session.add(
        JamfCatalogTitle(name_id="518", app_name="010 Editor", publisher="SweetScape", raw={})
    )
    await test_session.commit()

    resp = await client.get("/apps/jamf-index")
    assert resp.status_code == 200

    index = resp.json()
    assert "518" in index
    assert "my-editor" in index["518"]  # name_id resolved to the catalog slug
