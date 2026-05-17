"""
Tests for Mac App Store metadata ingestion.

Uses inline fixture records and ``httpx.MockTransport`` rather than hitting
Apple's live lookup endpoint. Keeps tests fast, deterministic, and offline.

Inter-request delay in :func:`fetch_mas_lookup` is monkeypatched to zero so
tests don't sit through real 3-second waits.
"""

from datetime import date

import httpx
import pytest
from patcher_api.ingest import mas as mas_module
from patcher_api.ingest.mas import (
    fetch_mas_lookup,
    ingest_mas_apps,
)
from patcher_api.models.mas import MasApp
from sqlalchemy import select

PAGES_RECORD = {
    "bundleId": "com.apple.iWork.Pages",
    "trackName": "Pages",
    "version": "14.2",
    "releaseDate": "2024-04-02T07:00:00Z",
    "releaseNotes": "This update contains stability and performance improvements.",
    "trackViewUrl": "https://apps.apple.com/us/app/pages/id409201541?mt=12",
    "minimumOsVersion": "13.0",
    "price": 0.0,
    "kind": "mac-software",
    "artistName": "Apple",
    # Real iTunes payloads have dozens of fields. Extra="ignore" should let
    # validation pass and these should land verbatim in raw.
    "wrapperType": "software",
    "trackId": 409201541,
}

# Defensive: an iOS app would have kind="software" (not mac-software). The
# bundleId is identical to a real iOS-only app. Ingest should skip it.
IOS_RECORD = {
    "bundleId": "com.example.iosapp",
    "trackName": "Some iOS App",
    "version": "2.0",
    "kind": "software",
    "artistName": "Example",
}

INVALID_RECORD = {
    # Missing required 'bundleId' field. Should be skipped, not blow up.
    "trackName": "No Bundle ID",
    "kind": "mac-software",
}


@pytest.fixture(autouse=True)
def _zero_inter_request_delay(monkeypatch):
    """Speed up tests that exercise the serial fetch loop."""
    monkeypatch.setattr(mas_module, "_INTER_REQUEST_DELAY_SECONDS", 0)


def _make_client(handler) -> httpx.AsyncClient:
    """Build an ``httpx.AsyncClient`` wired to the given mock handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_mas_lookup_returns_results_for_matching_bundle_ids():
    """A successful lookup returns the response's results array."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"resultCount": 1, "results": [PAGES_RECORD]},
        )

    client = _make_client(handler)
    results = await fetch_mas_lookup(["com.apple.iWork.Pages"], client=client)

    assert len(results) == 1
    assert results[0]["bundleId"] == "com.apple.iWork.Pages"


@pytest.mark.asyncio
async def test_fetch_mas_lookup_skips_zero_result_responses():
    """Apple returns resultCount=0 for unknown bundle IDs. Don't include those."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resultCount": 0, "results": []})

    client = _make_client(handler)
    results = await fetch_mas_lookup(["com.unknown.app"], client=client)

    assert results == []


@pytest.mark.asyncio
async def test_fetch_mas_lookup_continues_after_http_error():
    """A single bundle_id's failure doesn't abort the rest of the sweep."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503)  # transient error on first call
        return httpx.Response(200, json={"resultCount": 1, "results": [PAGES_RECORD]})

    client = _make_client(handler)
    results = await fetch_mas_lookup(["com.first.fail", "com.apple.iWork.Pages"], client=client)

    # The failed lookup is logged + skipped; Pages still lands.
    assert len(results) == 1
    assert results[0]["bundleId"] == "com.apple.iWork.Pages"


@pytest.mark.asyncio
async def test_ingest_stores_realistic_record(test_session):
    ingested, skipped = await ingest_mas_apps(test_session, [PAGES_RECORD])

    assert ingested == 1
    assert skipped == 0

    pages = await test_session.scalar(
        select(MasApp).where(MasApp.bundle_id == "com.apple.iWork.Pages")
    )
    assert pages is not None
    assert pages.name == "Pages"
    assert pages.version == "14.2"
    assert pages.release_date == date(2024, 4, 2)
    assert pages.store_url.startswith("https://apps.apple.com/")
    assert pages.minimum_os_version == "13.0"
    assert pages.price == 0.0
    # Full payload preserved for fields not modeled in the Pydantic schema
    assert pages.raw["trackId"] == 409201541
    assert pages.raw["artistName"] == "Apple"


@pytest.mark.asyncio
async def test_ingest_skips_non_mac_software_results(test_session):
    """An iOS app result for a bundle_id collision is filtered out."""
    ingested, skipped = await ingest_mas_apps(test_session, [IOS_RECORD])

    assert ingested == 0
    assert skipped == 1

    stored = (await test_session.scalars(select(MasApp))).all()
    assert stored == []


@pytest.mark.asyncio
async def test_ingest_skips_invalid_records_without_blocking_the_batch(test_session):
    """Validation failures don't poison the whole ingestion run."""
    ingested, skipped = await ingest_mas_apps(test_session, [PAGES_RECORD, INVALID_RECORD])

    assert ingested == 1
    assert skipped == 1

    pages = await test_session.scalar(
        select(MasApp).where(MasApp.bundle_id == "com.apple.iWork.Pages")
    )
    assert pages is not None


@pytest.mark.asyncio
async def test_ingest_handles_release_date_parse_failure_gracefully(test_session):
    """A malformed releaseDate string nulls the column but doesn't fail the record."""
    bad_date_record = {**PAGES_RECORD, "releaseDate": "not-a-date"}
    ingested, skipped = await ingest_mas_apps(test_session, [bad_date_record])

    assert ingested == 1
    pages = await test_session.scalar(
        select(MasApp).where(MasApp.bundle_id == "com.apple.iWork.Pages")
    )
    assert pages.release_date is None


@pytest.mark.asyncio
async def test_ingest_upserts_on_re_run(test_session):
    """Running ingestion twice updates the existing row rather than duplicating."""
    v1 = {**PAGES_RECORD, "version": "14.2"}
    v2 = {**PAGES_RECORD, "version": "14.3"}

    await ingest_mas_apps(test_session, [v1])
    await ingest_mas_apps(test_session, [v2])

    apps = (await test_session.scalars(select(MasApp))).all()
    assert len(apps) == 1
    assert apps[0].version == "14.3"
