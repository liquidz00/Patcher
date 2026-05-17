"""
Tests for AutoPkg recipe-index ingestion.

Uses inline fixture index payloads and ``httpx.MockTransport`` rather than
hitting the live autopkg/index repo. Keeps tests fast, deterministic, and
offline.
"""

import httpx
import pytest
from patcher_api.ingest.autopkg import fetch_autopkg_index, ingest_autopkg_index
from patcher_api.models.autopkg import AutopkgRecipe
from sqlalchemy import select

# Real upstream index.json shape: top-level dict with "identifiers" and
# "shortnames" maps. Identifiers is the authoritative map of recipes;
# shortnames is an inverted lookup we don't currently store.
FIREFOX_DOWNLOAD_IDENTIFIER = "com.github.autopkg.download.Firefox"
FIREFOX_DOWNLOAD_ENTRY = {
    "name": "Firefox",
    "description": "Downloads the latest Firefox release.",
    "repo": "autopkg/recipes",
    "path": "Mozilla/Firefox.download.recipe",
    "shortname": "Firefox.download",
    "inferred_type": "download",
    "children": [
        "com.github.autopkg.munki.Firefox",
        "com.github.autopkg.pkg.Firefox",
    ],
}

FIREFOX_MUNKI_IDENTIFIER = "com.github.autopkg.munki.Firefox"
FIREFOX_MUNKI_ENTRY = {
    "name": "Firefox",
    "description": "Downloads the latest Firefox and imports into Munki.",
    "repo": "autopkg/recipes",
    "path": "Mozilla/Firefox.munki.recipe",
    "parent": FIREFOX_DOWNLOAD_IDENTIFIER,
    "shortname": "Firefox.munki",
    "inferred_type": "munki",
    # Real entries carry many more fields; extra="ignore" should let
    # validation pass and the full payload should land in raw.
    "preprocessors": [],
}

INVALID_ENTRY = {
    # Missing required "name", "repo", "path", "shortname" fields.
    "description": "broken",
}


def _make_index_payload(identifiers: dict) -> dict:
    """Build a minimal upstream-shaped index payload."""
    return {"identifiers": identifiers, "shortnames": {}}


def _make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_autopkg_index_returns_decoded_payload():
    payload = _make_index_payload({FIREFOX_DOWNLOAD_IDENTIFIER: FIREFOX_DOWNLOAD_ENTRY})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _make_client(handler)
    result = await fetch_autopkg_index(client=client)

    assert "identifiers" in result
    assert FIREFOX_DOWNLOAD_IDENTIFIER in result["identifiers"]


@pytest.mark.asyncio
async def test_ingest_stores_recipe_with_expected_fields(test_session):
    payload = _make_index_payload({FIREFOX_DOWNLOAD_IDENTIFIER: FIREFOX_DOWNLOAD_ENTRY})

    ingested, skipped = await ingest_autopkg_index(test_session, payload)

    assert ingested == 1
    assert skipped == 0

    recipe = await test_session.scalar(
        select(AutopkgRecipe).where(AutopkgRecipe.identifier == FIREFOX_DOWNLOAD_IDENTIFIER)
    )
    assert recipe is not None
    assert recipe.name == "Firefox"
    assert recipe.shortname == "Firefox.download"
    assert recipe.repo == "autopkg/recipes"
    assert recipe.path == "Mozilla/Firefox.download.recipe"
    assert recipe.parent_identifier is None
    assert recipe.inferred_type == "download"
    # raw payload preserves the full upstream shape, including the children
    # list we don't project to its own column
    assert recipe.raw["children"] == FIREFOX_DOWNLOAD_ENTRY["children"]


@pytest.mark.asyncio
async def test_ingest_stores_parent_identifier_when_present(test_session):
    payload = _make_index_payload({FIREFOX_MUNKI_IDENTIFIER: FIREFOX_MUNKI_ENTRY})

    await ingest_autopkg_index(test_session, payload)

    recipe = await test_session.scalar(
        select(AutopkgRecipe).where(AutopkgRecipe.identifier == FIREFOX_MUNKI_IDENTIFIER)
    )
    assert recipe.parent_identifier == FIREFOX_DOWNLOAD_IDENTIFIER


@pytest.mark.asyncio
async def test_ingest_skips_invalid_records_without_blocking_the_batch(test_session):
    """Validation failures don't poison the whole ingestion run."""
    payload = _make_index_payload(
        {
            FIREFOX_DOWNLOAD_IDENTIFIER: FIREFOX_DOWNLOAD_ENTRY,
            "com.broken.entry": INVALID_ENTRY,
        }
    )

    ingested, skipped = await ingest_autopkg_index(test_session, payload)

    assert ingested == 1
    assert skipped == 1
    # Firefox should still have made it in
    recipe = await test_session.scalar(
        select(AutopkgRecipe).where(AutopkgRecipe.identifier == FIREFOX_DOWNLOAD_IDENTIFIER)
    )
    assert recipe is not None


@pytest.mark.asyncio
async def test_ingest_skips_non_dict_entries(test_session):
    """Defensive: if a recipe entry isn't a dict (corrupt upstream), skip + log."""
    payload = {"identifiers": {"com.broken.kind": "this should be a dict"}, "shortnames": {}}

    ingested, skipped = await ingest_autopkg_index(test_session, payload)

    assert ingested == 0
    assert skipped == 1


@pytest.mark.asyncio
async def test_ingest_handles_empty_payload(test_session):
    """No identifiers map (or empty one) is a non-error no-op."""
    ingested, skipped = await ingest_autopkg_index(test_session, {})

    assert ingested == 0
    assert skipped == 0


@pytest.mark.asyncio
async def test_ingest_upserts_on_re_run(test_session):
    """Running ingestion twice updates the existing row rather than duplicating."""
    v1 = _make_index_payload(
        {FIREFOX_DOWNLOAD_IDENTIFIER: {**FIREFOX_DOWNLOAD_ENTRY, "path": "old/path.recipe"}}
    )
    v2 = _make_index_payload(
        {FIREFOX_DOWNLOAD_IDENTIFIER: {**FIREFOX_DOWNLOAD_ENTRY, "path": "new/path.recipe"}}
    )

    await ingest_autopkg_index(test_session, v1)
    await ingest_autopkg_index(test_session, v2)

    recipes = (await test_session.scalars(select(AutopkgRecipe))).all()
    assert len(recipes) == 1
    assert recipes[0].path == "new/path.recipe"
