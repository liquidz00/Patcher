"""
Shared catalog query helpers for the MCP server.

Tools and resources both need to project app rows and compute catalog-level
aggregates. Centralizing the logic here keeps a tool and its mirror resource
(for example ``get_catalog_summary`` and ``catalog://summary``) from drifting
apart over time.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.app import App as AppSchema
from patcher_api.schemas.app import InstallMethod


def serialize_app(row: AppRow) -> dict:
    """
    Project an ``AppRow`` into the same dict shape the REST API returns.

    Routes through the public Pydantic schema with ``mode="json"`` so dates
    become ISO strings, ``HttpUrl`` becomes a plain string, and the
    ``InstallMethod`` enum becomes its string value.
    """
    return AppSchema.model_validate(row).model_dump(mode="json")


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


async def catalog_categories(session: AsyncSession) -> dict:
    """
    Distinct categorical values in the catalog.

    ``install_methods`` is the static :class:`InstallMethod` enum (the universe
    Patcher recognizes, not just values in use); ``sources`` and ``vendors``
    reflect what is actually present right now. Returned dict has keys
    ``install_methods`` (list[str]), ``sources`` (list[str], sorted), and
    ``vendors`` (list[str], sorted).
    """
    all_source_arrays = (await session.scalars(select(AppRow.sources))).all()
    sources = sorted({src for arr in all_source_arrays for src in (arr or [])})
    vendor_rows = (
        await session.scalars(select(AppRow.vendor).where(AppRow.vendor.is_not(None)).distinct())
    ).all()
    vendors = sorted(vendor_rows)
    return {
        "install_methods": [m.value for m in InstallMethod],
        "sources": sources,
        "vendors": vendors,
    }
