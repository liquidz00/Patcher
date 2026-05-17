from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.auth import get_current_user
from patcher_api.db import get_session
from patcher_api.labels import build_installomator_label
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.app import App
from patcher_api.schemas.labels import GenerateLabelResponse
from patcher_api.schemas.sources import AppSources

router = APIRouter(
    prefix="/apps",
    tags=["apps"],
    dependencies=[Depends(get_current_user)],
)


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

    Filters apply in order: ``vendor`` is pushed into the SQL WHERE clause;
    ``source`` and ``exclude_source`` are applied in Python after fetch
    (the ``sources`` column is a JSON list, not trivially queryable in
    SQLite without a JSON1 function). Pagination is applied last, after
    all filters, so ``limit`` describes the page size of the *filtered*
    result, not the raw table.

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

    rows = (await session.scalars(stmt)).all()

    if source is not None:
        rows = [r for r in rows if source in r.sources]
    if exclude_source is not None:
        rows = [r for r in rows if exclude_source not in r.sources]
    return list(rows[offset : offset + limit])


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
        }
    )


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

    if detail is None or (detail.homebrew_cask is None and detail.installomator is None):
        raise HTTPException(
            status_code=422,
            detail=(
                f"App '{slug}' has no source detail — cannot generate a label. "
                "This is usually a leftover seed record; expected for production data."
            ),
        )

    return build_installomator_label(app_row, detail)
