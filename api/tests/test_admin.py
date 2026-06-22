"""
Tests for the macOS resolver's admin ingest endpoint.

Covers the shared-secret gate (incl. fail-closed when unconfigured), the
update-only + validation + don't-clobber rules, and that a successful batch
re-stitches and refreshes the catalog ETag.
"""

import json
from types import SimpleNamespace

import pytest
from patcher_api.models.installomator import InstallomatorLabel
from sqlalchemy import select

from patcher.policy import RESOLUTION_EXCLUDED_LABELS

_TOKEN = "s3cret-admin-token"


def _ndjson(*records: dict) -> bytes:
    return "\n".join(json.dumps(r) for r in records).encode()


def _configure_token(monkeypatch, token: str) -> None:
    """Point the admin route's settings at a known token (get_settings is cached)."""
    monkeypatch.setattr(
        "patcher_api.routes.admin.get_settings",
        lambda: SimpleNamespace(admin_token=token),
    )


async def _add_label(session, name: str) -> None:
    session.add(
        InstallomatorLabel(
            name=name,
            display_name=name,
            install_type="dmg",
            raw={
                "name": name,
                "downloadURL": "$(curl -fsL https://example.com | grep ...)",
                "appNewVersion": "$(versionFromGit foo bar)",
            },
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_ingest_requires_token_configured(client, monkeypatch):
    """Fail-closed: no admin token set -> 503, never an open write surface."""
    _configure_token(monkeypatch, "")
    resp = await client.post(
        "/admin/labels/resolved",
        content=_ndjson({"label": "x", "ok": True}),
        headers={"Authorization": "Bearer anything"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_ingest_rejects_missing_and_wrong_token(client, monkeypatch):
    _configure_token(monkeypatch, _TOKEN)
    body = _ndjson({"label": "x", "ok": True})

    no_header = await client.post("/admin/labels/resolved", content=body)
    assert no_header.status_code == 401

    wrong = await client.post(
        "/admin/labels/resolved", content=body, headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_ingest_updates_only_existing_with_validation(client, test_session, monkeypatch):
    _configure_token(monkeypatch, _TOKEN)

    await _add_label(test_session, "googlechrome")
    await _add_label(test_session, "badurllabel")

    body = _ndjson(
        # resolves cleanly -> updated
        {
            "label": "googlechrome",
            "ok": True,
            "downloadURL": "https://dl.google.com/chrome/mac/stable/googlechrome.dmg",
            "appNewVersion": "149.0.7827.29",
        },
        # not ok -> never clobbers a good value
        {"label": "googlechrome", "ok": False, "error": "missing: downloadURL"},
        # exists but both fields are garbage -> skipped_invalid
        {
            "label": "badurllabel",
            "ok": True,
            "downloadURL": "ftp://example.com/x.dmg",
            "appNewVersion": "<html>nope</html>",
        },
        # not yet created by the Linux ingest -> skipped_unknown
        {
            "label": "brandnewlabel",
            "ok": True,
            "downloadURL": "https://example.com/new.dmg",
            "appNewVersion": "1.0",
        },
    )

    resp = await client.post(
        "/admin/labels/resolved",
        content=body,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    assert summary == {
        "received": 4,
        "updated": 1,
        "skipped_not_ok": 1,
        "skipped_invalid": 1,
        "skipped_unknown": 1,
        "malformed_lines": 0,
    }

    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "googlechrome")
    )
    assert row.download_url == "https://dl.google.com/chrome/mac/stable/googlechrome.dmg"
    assert row.app_new_version == "149.0.7827.29"
    assert row.resolution_source == "macos"
    assert row.resolved_at is not None

    # The garbage record left badurllabel untouched (NULL, not clobbered).
    bad = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "badurllabel")
    )
    assert bad.download_url is None
    assert bad.resolution_source is None


@pytest.mark.asyncio
async def test_unresolved_worklist_requires_token(client, monkeypatch):
    _configure_token(monkeypatch, _TOKEN)
    no_header = await client.get("/admin/labels/unresolved")
    assert no_header.status_code == 401


@pytest.mark.asyncio
async def test_unresolved_worklist_selects_the_right_labels(client, test_session, monkeypatch):
    _configure_token(monkeypatch, _TOKEN)

    dyn_url = "$(curl -fsL https://example.com | grep ...)"
    test_session.add_all(
        [
            # dynamic field Linux couldn't fill (NULL) -> needs macOS
            InstallomatorLabel(name="needs_null", raw={"downloadURL": dyn_url}, download_url=None),
            # macOS already owns it -> stays on the worklist to keep it fresh
            InstallomatorLabel(
                name="macos_owned",
                raw={"downloadURL": dyn_url},
                download_url="https://example.com/x.dmg",
                resolution_source="macos",
            ),
            # Linux resolved it (filled, no macOS stamp) -> excluded, refreshed for free
            InstallomatorLabel(
                name="linux_done",
                raw={"downloadURL": dyn_url},
                download_url="https://example.com/y.dmg",
            ),
            # literal label, nothing dynamic -> excluded
            InstallomatorLabel(
                name="literal",
                raw={"downloadURL": "https://example.com/z.dmg"},
                download_url="https://example.com/z.dmg",
            ),
        ]
    )
    await test_session.commit()

    resp = await client.get(
        "/admin/labels/unresolved", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert resp.status_code == 200
    assert resp.json()["labels"] == ["macos_owned", "needs_null"]


@pytest.mark.asyncio
async def test_unresolved_worklist_excludes_user_context_labels(client, test_session, monkeypatch):
    """User-context labels (resolve from the logged-in user) never go to the runner."""
    _configure_token(monkeypatch, _TOKEN)
    dyn = "$(curl -fsL https://example.com | grep ...)"
    test_session.add_all(
        [
            # would normally qualify (dynamic + NULL), but is user-context -> excluded
            InstallomatorLabel(
                name="thunderbird_intl", raw={"downloadURL": dyn}, download_url=None
            ),
            InstallomatorLabel(name="resolvable", raw={"downloadURL": dyn}, download_url=None),
        ]
    )
    await test_session.commit()

    resp = await client.get(
        "/admin/labels/unresolved", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert resp.json()["labels"] == ["resolvable"]


@pytest.mark.asyncio
async def test_unresolved_worklist_excludes_policy_labels(client, test_session, monkeypatch):
    """Labels in RESOLUTION_EXCLUDED_LABELS (discontinued/gated) never reach the runner."""
    _configure_token(monkeypatch, _TOKEN)
    excluded = next(iter(RESOLUTION_EXCLUDED_LABELS))  # any curated member
    dyn = "$(curl -fsL https://example.com | grep ...)"
    test_session.add_all(
        [
            # would normally qualify (dynamic + NULL), but is policy-excluded -> dropped
            InstallomatorLabel(name=excluded, raw={"downloadURL": dyn}, download_url=None),
            InstallomatorLabel(name="resolvable", raw={"downloadURL": dyn}, download_url=None),
        ]
    )
    await test_session.commit()

    resp = await client.get(
        "/admin/labels/unresolved", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert resp.json()["labels"] == ["resolvable"]


@pytest.mark.asyncio
async def test_ingest_coerces_array_shaped_values_to_first_scalar(
    client, test_session, monkeypatch
):
    """
    Regression: a label declares ``appNewVersion=( "$v.$b" )`` (bash array),
    resolveLabel.sh emits it as a JSON array, and the validator crashed on
    ``.strip()`` of a list — taking down the whole batch with a 500. The
    handler must coerce arrays to their first scalar (same pattern the Linux
    ingest uses) so one bad shape can't poison the run.
    """
    _configure_token(monkeypatch, _TOKEN)

    await _add_label(test_session, "arraylabel")

    body = _ndjson(
        {
            "label": "arraylabel",
            "ok": True,
            "downloadURL": ["https://example.com/arr.dmg"],
            "appNewVersion": ["1.2.3"],
        },
    )

    resp = await client.post(
        "/admin/labels/resolved",
        content=body,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 1
    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "arraylabel")
    )
    assert row.download_url == "https://example.com/arr.dmg"
    assert row.app_new_version == "1.2.3"


@pytest.mark.asyncio
async def test_ingest_decodes_html_entities_in_urls(client, test_session, monkeypatch):
    """
    A resolved URL that came back HTML-entity-encoded (``&amp;`` for ``&``) is
    decoded before validation, so the corrected URL is stored — not silently
    kept broken (``&amp;`` is a syntactically valid URL, so it slips past the
    clean-URL check otherwise).
    """
    _configure_token(monkeypatch, _TOKEN)

    await _add_label(test_session, "firefox_da")

    body = _ndjson(
        {
            "label": "firefox_da",
            "ok": True,
            "downloadURL": "https://download.mozilla.org/?product=firefox-latest&amp;os=osx&amp;lang=da",
            "appNewVersion": "152.0",
        },
    )

    resp = await client.post(
        "/admin/labels/resolved",
        content=body,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )

    assert resp.status_code == 200
    summary = resp.json()
    assert summary["updated"] == 1
    assert summary["skipped_invalid"] == 0

    row = await test_session.scalar(
        select(InstallomatorLabel).where(InstallomatorLabel.name == "firefox_da")
    )
    assert row.download_url == "https://download.mozilla.org/?product=firefox-latest&os=osx&lang=da"


@pytest.mark.asyncio
async def test_ingest_counts_malformed_lines(client, monkeypatch):
    _configure_token(monkeypatch, _TOKEN)

    body = b'{"label": "x", "ok": true}\nnot json at all\n{"ok": true}\n'
    resp = await client.post(
        "/admin/labels/resolved",
        content=body,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    assert resp.status_code == 200
    summary = resp.json()
    # line 1: known-or-unknown label; line 2: malformed; line 3: missing label key -> malformed
    assert summary["received"] == 3
    assert summary["malformed_lines"] == 2


def _configure_deploy(monkeypatch, *, token: str, sentinel_path: str) -> None:
    """Point the admin route's settings at a known token + deploy sentinel path."""
    monkeypatch.setattr(
        "patcher_api.routes.admin.get_settings",
        lambda: SimpleNamespace(admin_token=token, deploy_sentinel_path=sentinel_path),
    )


@pytest.mark.asyncio
async def test_deploy_rejects_missing_and_wrong_token(client, monkeypatch):
    _configure_deploy(monkeypatch, token=_TOKEN, sentinel_path="/tmp/unused")
    assert (await client.post("/admin/deploy")).status_code == 401
    wrong = await client.post("/admin/deploy", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_deploy_disabled_without_sentinel(client, monkeypatch):
    """Fail-closed: an unconfigured sentinel path means the endpoint is off."""
    _configure_deploy(monkeypatch, token=_TOKEN, sentinel_path="")
    resp = await client.post("/admin/deploy", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_deploy_touches_sentinel(client, monkeypatch, tmp_path):
    sentinel = tmp_path / ".deploy-requested"
    _configure_deploy(monkeypatch, token=_TOKEN, sentinel_path=str(sentinel))

    resp = await client.post("/admin/deploy", headers={"Authorization": f"Bearer {_TOKEN}"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "deploy requested"}
    assert sentinel.exists()
    assert sentinel.read_text()  # wrote an ISO timestamp
