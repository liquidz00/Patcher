"""
Tests for Jamf App Installers HTML-catalog ingestion.

Uses an inline fixture HTML payload mirroring the upstream table format
rather than hitting learn.jamf.com. Keeps tests fast and offline.
"""

import httpx
import pytest
from patcher_api.ingest.jamf_app_installers import (
    fetch_jamf_app_installers_html,
    ingest_jamf_app_installers,
    parse_jamf_app_installers_table,
)
from patcher_api.models.jamf_app_installers import JamfAppInstaller
from sqlalchemy import select

# Mirrors the upstream table cell pattern (headers attribute scoped to
# reference-7022__entry__N). Three rows: one Jamf-hosted (host upstream
# is "--"), two external-hosted with real domains.
FIXTURE_HTML = """
<div>
<table class="table">
    <thead class="thead">
        <tr class="row">
            <th class="entry colsep-1 rowsep-1" id="reference-7022__entry__1">Title Name</th>
            <th class="entry colsep-1 rowsep-1" id="reference-7022__entry__2">Source</th>
            <th class="entry colsep-1 rowsep-1" id="reference-7022__entry__3">Host Name</th>
        </tr>
    </thead>
    <tbody class="tbody">
        <tr class="row">
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__1">010 Editor</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__2">Jamf</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__3">--</td>
        </tr>
        <tr class="row">
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__1">8x8 Work</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__2">External</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__3">work-desktop-assets.8x8.com</td>
        </tr>
        <tr class="row">
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__1">AltTab</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__2">External</td>
            <td class="entry colsep-1 rowsep-1" headers="reference-7022__entry__3">github.com</td>
        </tr>
    </tbody>
</table>
</div>
"""

# HTML page with the right shell but no matching cells in the table
# (Jamf changed their attribute names, hypothetically).
NO_ROWS_HTML = """
<table><thead><tr><th>Title</th></tr></thead><tbody></tbody></table>
"""


def _make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_returns_raw_html():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=FIXTURE_HTML)

    client = _make_client(handler)
    result = await fetch_jamf_app_installers_html(client=client)
    assert "010 Editor" in result


def test_parse_extracts_rows_with_expected_fields():
    rows = parse_jamf_app_installers_table(FIXTURE_HTML)

    assert len(rows) == 3
    assert rows[0] == {"title": "010 Editor", "source": "Jamf", "host": None}
    assert rows[1] == {
        "title": "8x8 Work",
        "source": "External",
        "host": "work-desktop-assets.8x8.com",
    }
    assert rows[2] == {"title": "AltTab", "source": "External", "host": "github.com"}


def test_parse_normalizes_double_dash_to_none():
    """Upstream uses '--' for Jamf-hosted (no external host). Normalized to None."""
    rows = parse_jamf_app_installers_table(FIXTURE_HTML)
    jamf_hosted = [r for r in rows if r["source"] == "Jamf"]
    assert all(r["host"] is None for r in jamf_hosted)


def test_parse_returns_empty_list_on_no_matching_cells():
    """Defensive: page restructure should produce zero rows, not crash."""
    rows = parse_jamf_app_installers_table(NO_ROWS_HTML)
    assert rows == []


@pytest.mark.asyncio
async def test_ingest_stores_rows(test_session):
    rows = parse_jamf_app_installers_table(FIXTURE_HTML)
    ingested, skipped = await ingest_jamf_app_installers(test_session, rows)

    assert ingested == 3
    assert skipped == 0

    editor = await test_session.scalar(
        select(JamfAppInstaller).where(JamfAppInstaller.title == "010 Editor")
    )
    assert editor.source == "Jamf"
    assert editor.host is None

    eight_x_eight = await test_session.scalar(
        select(JamfAppInstaller).where(JamfAppInstaller.title == "8x8 Work")
    )
    assert eight_x_eight.source == "External"
    assert eight_x_eight.host == "work-desktop-assets.8x8.com"


@pytest.mark.asyncio
async def test_ingest_skips_invalid_source_values(test_session):
    """Pydantic Literal['Jamf', 'External'] rejects unexpected source values."""
    rows = [{"title": "Bad Source", "source": "Mystery Vendor", "host": None}]
    ingested, skipped = await ingest_jamf_app_installers(test_session, rows)

    assert ingested == 0
    assert skipped == 1


@pytest.mark.asyncio
async def test_ingest_upserts_on_re_run(test_session):
    """Running ingestion twice updates the existing row rather than duplicating."""
    v1 = [{"title": "010 Editor", "source": "Jamf", "host": None}]
    v2 = [{"title": "010 Editor", "source": "External", "host": "editor.example.com"}]

    await ingest_jamf_app_installers(test_session, v1)
    await ingest_jamf_app_installers(test_session, v2)

    rows = (await test_session.scalars(select(JamfAppInstaller))).all()
    assert len(rows) == 1
    assert rows[0].source == "External"
    assert rows[0].host == "editor.example.com"
