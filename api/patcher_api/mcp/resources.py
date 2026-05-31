"""
MCP resources exposed to clients.

Resources are application-controlled context an MCP client can read or pin
into a conversation, as opposed to tools the model decides to invoke. The
catalog resources mirror the read-only tools but address the data by URI, so
a client can attach "the catalog summary" or "the firefox record" to context
without spending a tool call. The query logic is shared with the tools via
:mod:`patcher_api.mcp._queries` so the two surfaces stay identical.
"""

from sqlalchemy import select

from patcher_api.db import get_session_maker
from patcher_api.mcp._queries import (
    catalog_categories,
    catalog_summary,
    serialize_app,
)
from patcher_api.mcp.server import mcp
from patcher_api.models.app import App as AppRow


@mcp.resource(
    "catalog://summary",
    name="Catalog Summary",
    description="Top-line catalog statistics: total apps and per-source coverage counts.",
    mime_type="application/json",
)
async def summary_resource() -> dict:
    """Catalog-level statistics, mirroring the ``get_catalog_summary`` tool."""
    async with get_session_maker()() as session:
        return await catalog_summary(session)


@mcp.resource(
    "catalog://categories",
    name="Catalog Categories",
    description="Distinct install methods, sources, and vendors present in the catalog.",
    mime_type="application/json",
)
async def categories_resource() -> dict:
    """Distinct categorical values, mirroring the ``list_categories`` tool."""
    async with get_session_maker()() as session:
        return await catalog_categories(session)


@mcp.resource(
    "catalog://apps/{slug}",
    name="Catalog App Record",
    description="The canonical catalog record for a single app, addressed by slug.",
    mime_type="application/json",
)
async def app_resource(slug: str) -> dict:
    """
    A single app's canonical projection, addressed by slug.

    Same shape as the ``get_app`` tool and ``GET /apps/{slug}``. Raises
    ``ValueError`` if no app with that slug exists in the catalog.
    """
    async with get_session_maker()() as session:
        row = await session.scalar(select(AppRow).where(AppRow.slug == slug))

    if row is None:
        raise ValueError(f"App with slug '{slug}' not found")

    return serialize_app(row)
