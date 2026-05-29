from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import get_session
from patcher_api.drift import detect_drift, extract_versions
from patcher_api.labels import build_installomator_label
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.app import App
from patcher_api.schemas.drift import DriftEntry, DriftResponse
from patcher_api.schemas.labels import GenerateLabelResponse
from patcher_api.schemas.sources import AppSources

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
    stmt = select(AppRow).order_by(AppRow.slug)
    if vendor is not None:
        stmt = stmt.where(AppRow.vendor.ilike(vendor))

    rows = (await session.scalars(stmt)).all()

    total_scanned = 0
    all_entries: list[DriftEntry] = []
    for row in rows:
        detail = row.source_detail
        if len(extract_versions(detail)) < 2:
            continue
        total_scanned += 1
        entry = detect_drift(row, detail)
        if entry is None:
            continue
        if source is not None and source not in {sv.source for sv in entry.versions}:
            continue
        all_entries.append(entry)

    page = all_entries[offset : offset + limit]
    return DriftResponse(
        total_scanned=total_scanned,
        total_with_drift=len(all_entries),
        entries=page,
    )


@router.get("/{slug}", response_model=App)
async def get_app(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> AppRow:
    row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with slug '{slug}' not found",
        )
    return row


@router.get("/{slug}/sources", response_model=AppSources)
async def get_app_sources(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> AppSources:
    app_row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
    if app_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with slug '{slug}' not found",
        )

    detail_row = await session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
    )
    if detail_row is None:
        return AppSources()

    return AppSources.model_validate(
        {
            "installomator": detail_row.installomator,
            "homebrew_cask": detail_row.homebrew_cask,
            "autopkg": detail_row.autopkg,
            "jamf_app_installer": detail_row.jamf_app_installer,
        }
    )


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


@router.post("/{slug}/generate-label", response_model=GenerateLabelResponse)
async def generate_label(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> GenerateLabelResponse:
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
    :rtype: :class:`patcher_api.schemas.labels.GenerateLabelResponse`
    """
    app_row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
    if app_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with slug '{slug}' not found",
        )

    detail = await session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
    )

    if detail is None or (
        detail.homebrew_cask is None
        and detail.installomator is None
        and detail.jamf_app_installer is None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"App '{slug}' has no source detail — cannot generate a label. "
                "This is usually a leftover seed record; expected for production data."
            ),
        )

    return build_installomator_label(app_row, detail)
