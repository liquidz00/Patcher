"""
Route tests for ``/apps/drift`` and ``/apps/{slug}/drift``.

The base seed has no naturally drifted apps (firefox is 121.0 == 121.0
across both sources, google-chrome's Installomator entry has no
``appNewVersion``). Tests that need drift inject a fixture app directly
into the test session.
"""

import pytest
import pytest_asyncio
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow


def _make_drift_app(
    *,
    slug,
    name,
    vendor,
    installomator_version,
    cask_version,
    bundle_id=None,
):
    row = AppRow(
        slug=slug,
        bundle_id=bundle_id,
        name=name,
        vendor=vendor,
        current_version=cask_version,
        latest_release_date=None,
        download_url=None,
        install_method=None,
        sha256=None,
        sources=["installomator", "homebrew_cask"],
        cves=[],
    )
    row.source_detail = AppSourceDetailRow(
        installomator={
            "label_name": slug,
            "label_url": f"https://example.test/{slug}",
            "raw": {"appNewVersion": installomator_version},
        },
        homebrew_cask={
            "token": slug,
            "cask_json": {"version": cask_version},
        },
    )
    return row


@pytest_asyncio.fixture
async def seeded_with_drift(test_session):
    """
    Seed plus three additional apps: one drifted, one agreed, one with an
    unparseable Cask version.
    """
    test_session.add_all(
        [
            _make_drift_app(
                slug="drift-slack",
                name="Drift Slack",
                vendor="Slack",
                installomator_version="4.32.0",
                cask_version="4.40.0",
            ),
            _make_drift_app(
                slug="agreed-zoom",
                name="Agreed Zoom",
                vendor="Zoom",
                installomator_version="5.17.5",
                cask_version="5.17.5",
            ),
            _make_drift_app(
                slug="drift-fantastical",
                name="Drift Fantastical",
                vendor="Flexibits",
                installomator_version="4.1.13",
                cask_version="2025-04-15",
            ),
        ]
    )
    await test_session.commit()
    return test_session


@pytest.mark.asyncio
async def test_list_drift_returns_empty_for_base_seed(client):
    """firefox is 121.0/121.0 and google-chrome has no installomator version."""
    response = await client.get("/apps/drift")

    assert response.status_code == 200
    body = response.json()
    assert body["total_with_drift"] == 0
    assert body["entries"] == []


@pytest.mark.asyncio
async def test_list_drift_returns_drifted_apps(seeded_with_drift, client):
    response = await client.get("/apps/drift")

    assert response.status_code == 200
    body = response.json()
    slugs = {entry["slug"] for entry in body["entries"]}
    assert slugs == {"drift-slack", "drift-fantastical"}
    assert body["total_with_drift"] == 2


@pytest.mark.asyncio
async def test_list_drift_total_scanned_counts_eligible_apps(seeded_with_drift, client):
    """total_scanned = apps with ≥2 versioned sources. firefox + drift-slack + agreed-zoom + drift-fantastical."""
    response = await client.get("/apps/drift")

    body = response.json()
    assert body["total_scanned"] == 4


@pytest.mark.asyncio
async def test_list_drift_filters_by_vendor(seeded_with_drift, client):
    response = await client.get("/apps/drift", params={"vendor": "Slack"})

    body = response.json()
    assert {entry["slug"] for entry in body["entries"]} == {"drift-slack"}


@pytest.mark.asyncio
async def test_list_drift_filters_by_source(seeded_with_drift, client):
    """All drift entries include installomator — filter is a smoke test."""
    response = await client.get("/apps/drift", params={"source": "installomator"})

    body = response.json()
    assert {entry["slug"] for entry in body["entries"]} == {"drift-slack", "drift-fantastical"}


@pytest.mark.asyncio
async def test_list_drift_source_filter_excludes_when_source_absent(seeded_with_drift, client):
    response = await client.get("/apps/drift", params={"source": "autopkg"})

    body = response.json()
    assert body["entries"] == []
    assert (
        body["total_with_drift"] == 0
    )  # ``total_with_drift`` reflects the filter, matching ``/apps``


@pytest.mark.asyncio
async def test_list_drift_pagination(seeded_with_drift, client):
    response = await client.get("/apps/drift", params={"limit": 1, "offset": 0})

    body = response.json()
    assert len(body["entries"]) == 1
    assert body["total_with_drift"] == 2


@pytest.mark.asyncio
async def test_list_drift_offset_skips(seeded_with_drift, client):
    """Sorted by slug — drift-fantastical, drift-slack. Offset 1 yields drift-slack."""
    response = await client.get("/apps/drift", params={"limit": 1, "offset": 1})

    body = response.json()
    assert [entry["slug"] for entry in body["entries"]] == ["drift-slack"]


@pytest.mark.asyncio
async def test_list_drift_rejects_invalid_limit(client):
    response = await client.get("/apps/drift", params={"limit": 0})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_drift_rejects_limit_above_max(client):
    response = await client.get("/apps/drift", params={"limit": 1001})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_drift_rejects_negative_offset(client):
    response = await client.get("/apps/drift", params={"offset": -1})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_drift_does_not_collide_with_slug_route(seeded_with_drift, client):
    """``/apps/drift`` must hit the list route, not be captured as slug=drift."""
    response = await client.get("/apps/drift")

    assert response.status_code == 200
    assert "entries" in response.json()


@pytest.mark.asyncio
async def test_get_app_drift_returns_entry_for_drifted_app(seeded_with_drift, client):
    response = await client.get("/apps/drift-slack/drift")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "drift-slack"
    assert body["leader"] == "homebrew_cask"
    assert body["laggard"] == "installomator"
    assert {v["source"] for v in body["versions"]} == {"installomator", "homebrew_cask"}


@pytest.mark.asyncio
async def test_get_app_drift_returns_null_for_agreed_app(seeded_with_drift, client):
    response = await client.get("/apps/agreed-zoom/drift")

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_app_drift_returns_null_for_single_source_app(client):
    """slack has only ``installomator`` in sources → no detail to compare against."""
    response = await client.get("/apps/slack/drift")

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.asyncio
async def test_get_app_drift_returns_404_for_unknown_slug(client):
    response = await client.get("/apps/nonexistent/drift")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
