"""
Tests for Homebrew Cask ingestion.

Uses inline fixture records rather than hitting the live API — keeps tests
fast, deterministic, and offline.
"""

import pytest
from patcher_api.ingest.homebrew import ingest_homebrew_casks
from patcher_api.models.homebrew import HomebrewCask
from sqlalchemy import select

FIREFOX_CASK = {
    "token": "firefox",
    "name": ["Mozilla Firefox"],
    "desc": "Web browser",
    "homepage": "https://www.mozilla.org/firefox/",
    "url": "https://download-installer.cdn.mozilla.net/pub/firefox/releases/121.0/mac/en-US/Firefox%20121.0.dmg",
    "version": "121.0",
    "sha256": "no_check",
    "auto_updates": True,
    "depends_on": {"macos": ">= :el_capitan"},
    "artifacts": [{"app": ["Firefox.app"]}, {"zap": []}],
    # Real Cask records carry many more fields — extra="ignore" should let
    # validation pass and these should land verbatim in `raw`.
    "tap": "homebrew/cask",
    "ruby_source_path": "Casks/f/firefox.rb",
}

MINIMAL_CASK = {
    "token": "minimal-cask",
    "name": [],
    # Every other optional field omitted on purpose
}

INVALID_CASK = {
    # Missing the required 'token' field — should be skipped, not blow up
    "name": ["No Token"],
}


@pytest.mark.asyncio
async def test_ingest_stores_realistic_record(test_session):
    ingested, skipped = await ingest_homebrew_casks(test_session, [FIREFOX_CASK])

    assert ingested == 1
    assert skipped == 0

    cask = await test_session.scalar(select(HomebrewCask).where(HomebrewCask.token == "firefox"))
    assert cask is not None
    assert cask.name == "Mozilla Firefox"
    assert cask.version == "121.0"
    assert cask.desc == "Web browser"
    # Raw payload preserves fields not modeled in the Pydantic schema
    assert cask.raw["tap"] == "homebrew/cask"
    assert cask.raw["ruby_source_path"] == "Casks/f/firefox.rb"


@pytest.mark.asyncio
async def test_ingest_handles_record_with_empty_name_list(test_session):
    """Falls back to the token when the upstream name list is empty."""
    ingested, _ = await ingest_homebrew_casks(test_session, [MINIMAL_CASK])

    assert ingested == 1
    cask = await test_session.scalar(
        select(HomebrewCask).where(HomebrewCask.token == "minimal-cask")
    )
    assert cask.name == "minimal-cask"


@pytest.mark.asyncio
async def test_ingest_skips_invalid_records_without_blocking_the_batch(test_session):
    """Validation failures don't poison the whole ingestion run."""
    ingested, skipped = await ingest_homebrew_casks(test_session, [FIREFOX_CASK, INVALID_CASK])

    assert ingested == 1
    assert skipped == 1
    # Firefox should still have made it in despite the invalid record alongside
    cask = await test_session.scalar(select(HomebrewCask).where(HomebrewCask.token == "firefox"))
    assert cask is not None


@pytest.mark.asyncio
async def test_ingest_upserts_on_re_run(test_session):
    """Running ingestion twice updates the existing row rather than duplicating."""
    v1 = {**FIREFOX_CASK, "version": "121.0"}
    v2 = {**FIREFOX_CASK, "version": "122.0"}

    await ingest_homebrew_casks(test_session, [v1])
    await ingest_homebrew_casks(test_session, [v2])

    casks = (await test_session.scalars(select(HomebrewCask))).all()
    assert len(casks) == 1
    assert casks[0].version == "122.0"
