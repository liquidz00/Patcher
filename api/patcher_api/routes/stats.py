from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.db import get_session
from patcher_api.queries import catalog_last_refresh, catalog_summary
from patcher_api.schemas.stats import CatalogStats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=CatalogStats)
async def get_stats(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CatalogStats:
    summary = await catalog_summary(session)
    return CatalogStats(
        total_apps=summary["total_apps"],
        sources=summary["sources"],
        last_refresh=await catalog_last_refresh(session),
        catalog_sha=getattr(request.app.state, "catalog_sha", None),
    )
