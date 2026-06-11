"""
Admin write surface — the macOS resolver's ingest endpoint.

A label is a zsh program: faithfully resolving its ``downloadURL`` /
``appNewVersion`` means running the real fragment on macOS (``getJSONValue``
via osascript, ``$(arch)``, vendor curls). The Linux host can't do that, so a
scheduled GitHub macOS runner resolves every label with ``resolveLabel.sh
--json`` and POSTs the NDJSON here. This endpoint validates and upserts those
values into the rows the Linux ingest already created, re-stitches, and
refreshes the catalog ETag.

Reads stay public; this one write route is gated by a shared secret
(``PATCHER_API_ADMIN_TOKEN``). The endpoint is fail-closed: with no token
configured it refuses every request, so a misconfigured host can't expose an
open write surface.
"""

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.catalog import recompute_catalog_sha
from patcher_api.config import get_settings
from patcher_api.db import get_session
from patcher_api.installomator.ingest import (
    _MACOS_SOURCE,
    USER_CONTEXT_LABELS,
    _scalar_for_column,
)
from patcher_api.installomator.resolver import (
    is_shell_expression,
    looks_like_clean_http_url,
    looks_like_clean_version,
)
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.stitch import stitch_catalog

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class ResolvedIngestSummary(BaseModel):
    """Per-upload accounting returned to the runner so a CI step can assert on it."""

    received: int
    updated: int
    skipped_not_ok: int
    skipped_invalid: int
    skipped_unknown: int
    malformed_lines: int


class UnresolvedLabels(BaseModel):
    """Worklist the macOS runner fetches: label names that need macOS resolution."""

    labels: list[str]


class DeployResponse(BaseModel):
    """Acknowledges that a deploy was requested (the sentinel was touched)."""

    status: str


def _needs_macos_resolution(row: InstallomatorLabel) -> bool:
    """
    True if a label needs the macOS runner rather than the Linux resolver.

    Two cases: a dynamic field the Linux resolver couldn't fill (still NULL), or
    a row macOS already owns (re-resolved each run since the Linux refresh can't
    keep those fresh). Labels the Linux resolver fully handled are excluded — it
    refreshes them daily on the box for free. User-context labels are excluded
    outright: they resolve from the logged-in user, so no headless run can.
    """
    if row.name in USER_CONTEXT_LABELS:
        return False
    if row.resolution_source == _MACOS_SOURCE:
        return True
    download_url = _scalar_for_column(row.raw.get("downloadURL"))
    app_new_version = _scalar_for_column(row.raw.get("appNewVersion"))
    return (is_shell_expression(download_url) and row.download_url is None) or (
        is_shell_expression(app_new_version) and row.app_new_version is None
    )


def require_admin(authorization: str | None = Header(default=None)) -> None:
    """
    Gate a route on the shared admin secret.

    Fail-closed: an unset ``PATCHER_API_ADMIN_TOKEN`` returns 503 (endpoint
    disabled) rather than allowing the request, so forgetting to configure the
    secret can never silently open the write surface. ``compare_digest`` keeps
    the check constant-time.
    """
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="Admin endpoint disabled: no admin token set.")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")


@router.get(
    "/labels/unresolved",
    response_model=UnresolvedLabels,
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def list_unresolved_labels(
    session: AsyncSession = Depends(get_session),
) -> UnresolvedLabels:
    """
    The macOS runner's worklist: labels the Linux resolver couldn't resolve,
    plus the ones macOS already owns (re-resolved each run to stay fresh).

    The read half of the resolver handshake — the runner GETs this, resolves
    only these labels, and POSTs the results back to ``/labels/resolved``. This
    keeps each runner pass to the ~gap Linux can't cover instead of every label.
    """
    rows = (await session.execute(select(InstallomatorLabel))).scalars().all()
    return UnresolvedLabels(labels=sorted(r.name for r in rows if _needs_macos_resolution(r)))


@router.post(
    "/labels/resolved",
    response_model=ResolvedIngestSummary,
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def ingest_resolved_labels(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ResolvedIngestSummary:
    """
    Ingest macOS-resolved label values from an NDJSON stream.

    Body is ``application/x-ndjson``: one ``resolveLabel.sh --json`` record per
    line. For each record we update *only* the ``download_url`` /
    ``app_new_version`` of the label the Linux ingest already created — never
    creating rows (the Linux ingest is the sole owner of row existence and the
    structural columns). The rules:

    - ``ok:false`` records are skipped, so a failed vendor scrape never clobbers
      a previously-good value.
    - each value must pass the same sanity check the API serves through
      (:func:`looks_like_clean_http_url` / :func:`looks_like_clean_version`); a
      field that fails is dropped, not written.
    - rows updated are stamped ``resolution_source="macos"`` + ``resolved_at`` so
      the Linux refresh defers to them while they're fresh.

    After the batch the catalog is re-stitched (so ``/apps`` reflects the new
    values) and the ETag recomputed (so caches don't pin to the pre-upload
    hash).
    """
    body = await request.body()
    now = datetime.now(UTC)

    received = updated = skipped_not_ok = skipped_invalid = skipped_unknown = malformed = 0

    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        received += 1
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            malformed += 1
            continue

        name = record.get("label")
        if not name:
            malformed += 1
            continue
        if not record.get("ok"):
            skipped_not_ok += 1
            continue

        values: dict[str, object] = {}
        download_url = _scalar_for_column(record.get("downloadURL"))
        app_new_version = _scalar_for_column(record.get("appNewVersion"))
        if download_url and looks_like_clean_http_url(download_url):
            values["download_url"] = download_url
        if app_new_version and looks_like_clean_version(app_new_version):
            values["app_new_version"] = app_new_version
        if not values:
            skipped_invalid += 1
            continue

        values["resolution_source"] = _MACOS_SOURCE
        values["resolved_at"] = now
        result = await session.execute(
            update(InstallomatorLabel).where(InstallomatorLabel.name == name).values(**values)
        )
        if result.rowcount == 0:
            # Update-only: a label the Linux ingest hasn't created yet. It will
            # appear on the next daily ingest and resolve on the next runner pass.
            skipped_unknown += 1
        else:
            updated += 1

    await session.commit()

    if updated:
        # New values only reach the public /apps catalog through stitch, and the
        # ETag must move or revalidating clients keep getting the stale catalog.
        await stitch_catalog(session)
        # WAL parks commits in the -wal file; checkpoint so the on-disk .db
        # reflects them before we hash it, or the ETag wouldn't change and
        # caches would keep serving the pre-upload catalog.
        await session.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        recompute_catalog_sha(request.app)

    summary = ResolvedIngestSummary(
        received=received,
        updated=updated,
        skipped_not_ok=skipped_not_ok,
        skipped_invalid=skipped_invalid,
        skipped_unknown=skipped_unknown,
        malformed_lines=malformed,
    )
    log.info("Resolved-label ingest: %s", summary.model_dump())
    return summary


def _touch_sentinel(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).isoformat())


@router.post(
    "/deploy",
    response_model=DeployResponse,
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)
async def request_deploy() -> DeployResponse:
    """
    Request a code redeploy by touching the deploy sentinel file.

    The endpoint does no work itself: it touches a sentinel that a
    ``systemd.path`` unit watches, which runs the real deploy (guarded git
    pull, ``uv sync``, ``alembic upgrade head``, service restart) out of
    process. Reaching the box this way (public tunnel, deploy-token-gated)
    avoids opening an inbound SSH surface. Fail-closed: with no
    ``PATCHER_API_DEPLOY_SENTINEL_PATH`` set, the endpoint is disabled.
    """
    sentinel_path = get_settings().deploy_sentinel_path
    if not sentinel_path:
        raise HTTPException(
            status_code=503, detail="Deploy endpoint disabled: no sentinel path set."
        )
    await asyncio.to_thread(_touch_sentinel, Path(sentinel_path))
    log.info("Deploy requested; touched sentinel %s", sentinel_path)
    return DeployResponse(status="deploy requested")
