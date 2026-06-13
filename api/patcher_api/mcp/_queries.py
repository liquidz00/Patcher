"""
MCP-specific catalog query helpers (row projection + categorical values).

Catalog-level aggregates shared with the REST API (``catalog_summary``) live in
:mod:`patcher_api.queries` and are re-exported here so the MCP tools and their
mirror resources keep importing from one place.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.catalog import App as AppSchema
from patcher.catalog import InstallMethod
from patcher_api.models.app import App as AppRow
from patcher_api.queries import catalog_summary

__all__ = ["catalog_categories", "catalog_summary", "serialize_app"]


def serialize_app(row: AppRow) -> dict:
    """
    Project an ``AppRow`` into the same dict shape the REST API returns.

    Routes through the public Pydantic schema with ``mode="json"`` so dates
    become ISO strings, ``HttpUrl`` becomes a plain string, and the
    ``InstallMethod`` enum becomes its string value.
    """
    return AppSchema.model_validate(row).model_dump(mode="json")


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
