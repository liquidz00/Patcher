"""Public ``/apps`` routes: catalog lookups, per-source detail, drift, label generation, the jamf-index."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.catalog import App, AppSources, DriftEntry, DriftResponse, GeneratedLabel
from patcher_api import services
from patcher_api.db import get_session
from patcher_api.drift import detect_drift
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.jamf import JamfCatalogTitle
from patcher_api.services import AppNotFound, NoSourceDetail
from patcher_api.stitch import _normalize_name

router = APIRouter(
    prefix="/apps",
    tags=["apps"],
)


def _sources_contains(source_name: str) -> ColumnElement[bool]:
    """
    SQLite JSON1-backed predicate: ``source_name in apps.sources``.

    Renders as ``EXISTS (SELECT 1 FROM json_each(apps.sources) WHERE value
    = :source_name)``. Works for both ``source`` (include) and
    ``exclude_source`` (negate with ``~``) filters, lets SQL apply the
    predicate before pagination so ``LIMIT`` reflects the filtered count.

    JSON1 is built into the sqlite3 module Python ships against; no
    additional dependency. The predicate scales linearly with the
    ``sources`` array length (always small, at most 5 elements with the
    current source set) so the inner scan is effectively constant time.
    """
    je = func.json_each(AppRow.sources).table_valued("value")
    return select(literal(1)).select_from(je).where(je.c.value == source_name).exists()


@router.get("", response_model=list[App])
async def list_apps(
    vendor: str | None = None,
    source: str | None = None,
    exclude_source: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[AppRow]:
    """
    List apps in the catalog with optional filters and pagination.

    All filters (``vendor``, ``source``, ``exclude_source``) and the
    ``limit``/``offset`` pagination push down into a single SQL statement
    so the database does the filtering before paginating. Earlier versions
    of this endpoint filtered ``source``/``exclude_source`` in Python after
    materializing every row that matched ``vendor``, which made ``limit``
    describe the post-fetch slice rather than the actual page size.

    Results are ordered by ``slug`` so pagination is deterministic across
    requests.

    :param vendor: Case-insensitive exact vendor match. None disables.
    :param source: Include only rows whose ``sources`` contains this token.
    :param exclude_source: Drop rows whose ``sources`` contains this token.
    :param limit: Maximum rows to return. Default 100, max 1000.
    :param offset: Number of filtered rows to skip before returning. Default 0.
    """
    stmt = select(AppRow).order_by(AppRow.slug)
    if vendor is not None:
        stmt = stmt.where(AppRow.vendor.ilike(vendor))
    if source is not None:
        stmt = stmt.where(_sources_contains(source))
    if exclude_source is not None:
        stmt = stmt.where(~_sources_contains(exclude_source))
    stmt = stmt.limit(limit).offset(offset)

    rows = (await session.scalars(stmt)).all()
    return list(rows)


@router.get("/jamf-index", response_model=dict[str, list[str]])
async def jamf_index(session: AsyncSession = Depends(get_session)) -> dict[str, list[str]]:
    """
    Map each Jamf ``softwareTitleNameId`` to the catalog slug(s) it covers.

    Two contributing passes, unioned:

    - **Jamf App Installer codes** — precise, bundle/name-stitched at ingest
      time, read from ``app_source_detail.jamf_app_installer.jamf_id``.
    - **The full Jamf patch-title catalog** (``jamf_titles``) — every available
      Patch Management title, matched to catalog apps by normalized name. This
      extends coverage well beyond the App Installer subset.

    Clients fetch this index once and resolve patch-title codes to catalog
    slugs locally.
    """
    index: dict[str, set[str]] = {}

    # Pass 1: Jamf App Installer codes (precise, already stitched onto apps).
    jai_stmt = (
        select(AppRow.slug, AppSourceDetailRow.jamf_app_installer)
        .join(AppSourceDetailRow, AppSourceDetailRow.app_id == AppRow.id)
        .where(func.json_extract(AppSourceDetailRow.jamf_app_installer, "$.jamf_id").isnot(None))
    )
    for slug, jai in (await session.execute(jai_stmt)).all():
        index.setdefault(jai["jamf_id"], set()).add(slug)

    # Pass 2: the full patch-title catalog, matched to apps by normalized name.
    apps_by_norm: dict[str, list[str]] = {}
    for slug, name in (await session.execute(select(AppRow.slug, AppRow.name))).all():
        apps_by_norm.setdefault(_normalize_name(name), []).append(slug)
    title_stmt = select(JamfCatalogTitle.name_id, JamfCatalogTitle.app_name)
    for name_id, app_name in (await session.execute(title_stmt)).all():
        for slug in apps_by_norm.get(_normalize_name(app_name), []):
            index.setdefault(name_id, set()).add(slug)

    return {code: sorted(slugs) for code, slugs in sorted(index.items())}


@router.get("/drift", response_model=DriftResponse)
async def list_drift(
    vendor: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> DriftResponse:
    """
    Scan the catalog for cross-source version drift.

    Iterates apps with at least two versioned sources, compares their
    reported versions, and returns those whose sources disagree on what
    "latest" means. Drift is computed in Python after a single SQL fetch
    (drift cannot be expressed as a SQL filter without materializing the
    JSON payloads). ``total_scanned`` reflects the number of apps with
    enough sources to assess drift; ``total_with_drift`` is the unpaged
    count of disagreements.

    :param vendor: Case-insensitive exact vendor match. None disables.
    :param source: When set, drop entries where this source did not
        participate in the disagreement.
    :param limit: Max entries on this page. Default 100, max 1000.
    :param offset: Entries to skip before the page. Default 0.
    """
    return await services.scan_catalog_drift(
        session, vendor=vendor, source=source, limit=limit, offset=offset
    )


@router.get("/{slug}", response_model=App)
async def get_app(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> AppRow:
    try:
        return await services.get_app(session, slug)
    except AppNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{slug}/sources", response_model=AppSources)
async def get_app_sources(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> AppSources:
    try:
        return await services.get_app_sources(session, slug)
    except AppNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{slug}/drift", response_model=DriftEntry | None)
async def get_app_drift(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> DriftEntry | None:
    """
    Drift detection for a single app.

    Returns ``null`` when the app exists but has no drift (either fewer
    than two versioned sources, or every source agrees). 404 if the slug
    is unknown.

    :param slug: URL-friendly app identifier.
    """
    app_row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
    if app_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with slug '{slug}' not found",
        )
    return detect_drift(app_row, app_row.source_detail)


@router.post("/{slug}/generate-label", response_model=GeneratedLabel)
async def generate_label(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> GeneratedLabel:
    """
    Generate an Installomator label for ``slug``.

    Projects the app's Homebrew Cask + Installomator source payloads into
    an Installomator label fragment that consumers can drop into their
    Installomator deployments. Returns the label plus provenance metadata
    (which sources contributed) and any warnings about fields that couldn't
    be resolved (most commonly ``expectedTeamID`` for Cask-only apps).

    :param slug: URL-friendly app identifier.
    :type slug: str
    :param session: Async SQLAlchemy session (injected).
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :raises HTTPException: 404 if ``slug`` doesn't exist; 422 if the app has
        no source detail attached (rare — usually a leftover seed record).
    :return: The generated label content + metadata.
    :rtype: :class:`patcher_api.schemas.labels.GeneratedLabel`
    """
    try:
        return await services.generate_label(session, slug)
    except AppNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NoSourceDetail as exc:
        raise HTTPException(status_code=422, detail=str(exc))
