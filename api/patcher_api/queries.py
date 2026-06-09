"""
Catalog-level query helpers shared by the REST API and the MCP server.

Aggregates that summarize the whole catalog (counts, source coverage,
freshness) live here so both surfaces report identical numbers instead of
drifting. Per-surface row projection (the MCP serializers) stays in
:mod:`patcher_api.mcp._queries`.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.models.jamf import JamfAppInstaller
from patcher_api.models.mas import MasApp

# Source tables stamped at ingest; the newest stamp is the catalog's last refresh.
_INGEST_MODELS = (InstallomatorLabel, HomebrewCask, AutopkgRecipe, JamfAppInstaller, MasApp)


async def catalog_summary(session: AsyncSession) -> dict:
    """
    Total app count plus per-source coverage counts.

    Returned dict has ``total_apps`` (int) and ``sources`` (a dict mapping each
    upstream source name to the count of apps carrying that source's data).
    """
    total = (await session.scalar(select(func.count(AppRow.id)))) or 0
    # JSON null and SQL NULL both deserialize to Python None, so a SQL
    # COUNT(column) would over-count. Count truthiness in Python instead.
    details = (await session.scalars(select(AppSourceDetailRow))).all()
    sources = {
        "installomator": sum(1 for d in details if d.installomator),
        "homebrew_cask": sum(1 for d in details if d.homebrew_cask),
        "jamf_app_installer": sum(1 for d in details if d.jamf_app_installer),
        "autopkg": sum(1 for d in details if d.autopkg),
    }
    return {"total_apps": total, "sources": sources}


async def catalog_last_refresh(session: AsyncSession) -> datetime | None:
    """
    Newest ``ingested_at`` across all source tables, or ``None`` when empty.

    The daily refresh stamps freshly ingested rows, so the latest stamp is when
    the catalog last changed. Used as the ``/stats`` freshness signal.
    """
    stamps = [await session.scalar(select(func.max(m.ingested_at))) for m in _INGEST_MODELS]
    present = [s for s in stamps if s is not None]
    if not present:
        return None
    # SQLite returns naive datetimes; the stamps are written in UTC, so label them.
    newest = max(present)
    return newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
