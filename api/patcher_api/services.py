"""
Per-app catalog service functions shared by the REST routes and the MCP tools.

Both surfaces need the same "fetch this app, project its sources, build its
label, scan its drift" logic. Keeping it here instead of duplicated in each
handler is what stops the two from drifting — a fix in one place fixes both
(the kind of split that previously let a bug live in two copies at once).

Not-found and missing-detail conditions raise domain exceptions
(:class:`AppNotFound`, :class:`NoSourceDetail`); each surface translates them to
its own error shape — the REST routes to ``HTTPException``, the MCP tools to a
tool error.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.catalog import AppSources, DriftResponse, GeneratedLabel
from patcher_api.drift import scan_drift
from patcher_api.labels import build_installomator_label
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow


class AppNotFound(Exception):
    """Raised when no catalog app has the requested slug."""

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"App with slug '{slug}' not found")


class NoSourceDetail(Exception):
    """Raised when an app exists but has no upstream source detail to project."""

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(
            f"App '{slug}' has no source detail, cannot generate a label. "
            "This is usually a leftover seed record; expected for production data."
        )


async def get_app(session: AsyncSession, slug: str) -> AppRow:
    """Fetch one app row by slug. Raises :class:`AppNotFound` if unknown."""
    row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
    if row is None:
        raise AppNotFound(slug)
    return row


async def get_app_sources(session: AsyncSession, slug: str) -> AppSources:
    """
    Per-source payloads for ``slug``. Raises :class:`AppNotFound` if the slug is
    unknown; returns an all-``None`` :class:`AppSources` when the app exists but
    carries no source detail.
    """
    app_row = await get_app(session, slug)
    detail = await session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
    )
    if detail is None:
        return AppSources()
    return AppSources.model_validate(
        {
            "installomator": detail.installomator,
            "homebrew_cask": detail.homebrew_cask,
            "autopkg": detail.autopkg,
            "jamf_app_installer": detail.jamf_app_installer,
        }
    )


async def generate_label(session: AsyncSession, slug: str) -> GeneratedLabel:
    """
    Build the Installomator label projection for ``slug``. Raises
    :class:`AppNotFound` if unknown, :class:`NoSourceDetail` if the app has no
    upstream coverage to project.
    """
    app_row = await get_app(session, slug)
    detail = await session.scalar(
        select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
    )
    if detail is None or (
        detail.homebrew_cask is None
        and detail.installomator is None
        and detail.jamf_app_installer is None
    ):
        raise NoSourceDetail(slug)
    return build_installomator_label(app_row, detail)


async def scan_catalog_drift(
    session: AsyncSession,
    *,
    vendor: str | None,
    source: str | None,
    limit: int,
    offset: int,
) -> DriftResponse:
    """Vendor-filtered cross-source drift scan over the whole catalog."""
    stmt = select(AppRow).order_by(AppRow.slug)
    if vendor is not None:
        stmt = stmt.where(AppRow.vendor.ilike(vendor))
    rows = (await session.scalars(stmt)).all()
    return scan_drift(rows, source=source, limit=limit, offset=offset)
