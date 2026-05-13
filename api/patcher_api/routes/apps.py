from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import get_session
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.app import App
from patcher_api.schemas.sources import AppSources

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("", response_model=list[App])
async def list_apps(
    vendor: str | None = None,
    source: str | None = None,
    exclude_source: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[AppRow]:
    stmt = select(AppRow)
    if vendor is not None:
        stmt = stmt.where(AppRow.vendor.ilike(vendor))

    rows = (await session.scalars(stmt)).all()

    if source is not None:
        rows = [r for r in rows if source in r.sources]
    if exclude_source is not None:
        rows = [r for r in rows if exclude_source not in r.sources]
    return list(rows)


@router.get("/{bundle_id}", response_model=App)
async def get_app(
    bundle_id: str,
    session: AsyncSession = Depends(get_session),
) -> AppRow:
    row = await session.get(AppRow, bundle_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with bundle_id '{bundle_id}' not found",
        )
    return row


@router.get("/{bundle_id}/sources", response_model=AppSources)
async def get_app_sources(
    bundle_id: str,
    session: AsyncSession = Depends(get_session),
) -> AppSources:
    app_row = await session.get(AppRow, bundle_id)
    if app_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"App with bundle_id '{bundle_id}' not found",
        )

    detail_row = await session.get(AppSourceDetailRow, bundle_id)
    if detail_row is None:
        return AppSources()

    return AppSources.model_validate(
        {
            "installomator": detail_row.installomator,
            "homebrew_cask": detail_row.homebrew_cask,
            "autopkg": detail_row.autopkg,
        }
    )
