"""
MCP tools exposed to clients.

Each ``@mcp.tool`` decorator registers a callable that an MCP client (Claude
or otherwise) can invoke. The function signature becomes the tool's JSON
schema, so parameters must be typed and the docstring is what the client's
LLM reads to decide when to call it: be specific about what the tool returns
and what inputs it expects.

Tools acquire their own DB sessions via :func:`get_session_maker` rather
than through FastAPI's ``Depends`` injection, which is REST-specific. App
records are projected through :class:`patcher_api.schemas.app.App` so the
shape an MCP client sees is identical to ``GET /apps/{slug}``.
"""

from sqlalchemy import func, or_, select

from patcher_api.db import get_session_maker
from patcher_api.drift import detect_drift, extract_versions
from patcher_api.mcp.server import mcp
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.app import App as AppSchema
from patcher_api.schemas.app import InstallMethod
from patcher_api.schemas.drift import DriftEntry, DriftResponse


def _serialize_app(row: AppRow) -> dict:
    """
    Project an ``AppRow`` into the same dict shape the REST API returns.

    Routes through the public Pydantic schema with ``mode="json"`` so dates
    become ISO strings, ``HttpUrl`` becomes a plain string, and the
    ``InstallMethod`` enum becomes its string value. Keeping the conversion
    here means the two tools that return apps stay structurally identical
    to ``GET /apps/{slug}`` automatically.
    """
    return AppSchema.model_validate(row).model_dump(mode="json")


@mcp.tool
async def get_catalog_summary() -> dict:
    """
    Return top-line statistics about the Patcher catalog: the total number
    of apps and per-source coverage counts (how many apps have data from
    each upstream source: Installomator, Homebrew Cask, Jamf App Installer,
    AutoPkg). Useful to orient on what data is available before drilling
    into specific apps with ``search_apps`` or ``get_app``.

    Returned dict has keys ``total_apps`` (int) and ``sources`` (a dict
    mapping each source name to the count of apps carrying that source's
    data).
    """
    async with get_session_maker()() as session:
        total = (await session.scalar(select(func.count(AppRow.id)))) or 0
        # Per-source counts have to be done in Python rather than SQL
        # ``COUNT(column)``: SQLAlchemy's ``JSON`` type stores Python ``None``
        # as the JSON ``null`` literal (non-empty TEXT), which the SQL
        # aggregate would over-count. SQLAlchemy deserializes both SQL NULL
        # and JSON null back to Python ``None`` on read, so a truthiness
        # check here is correct regardless of how the row was written.
        details = (await session.scalars(select(AppSourceDetailRow))).all()
        sources = {
            "installomator": sum(1 for d in details if d.installomator),
            "homebrew_cask": sum(1 for d in details if d.homebrew_cask),
            "jamf_app_installer": sum(1 for d in details if d.jamf_app_installer),
            "autopkg": sum(1 for d in details if d.autopkg),
        }

    return {"total_apps": total, "sources": sources}


@mcp.tool
async def search_apps(query: str, limit: int = 20) -> list[dict]:
    """
    Search the catalog for apps matching ``query``.

    Performs a case-insensitive substring match against each app's slug,
    name, vendor, and bundle_id. Useful for fuzzy lookups when the caller
    knows part of an app's identity but not its exact slug (e.g. "firefox"
    hits ``firefox``, ``firefoxesr``, ``firefoxpkg``). Results are ordered
    by slug for deterministic paging across repeated queries.

    ``query`` is required but may be empty, in which case everything up to
    ``limit`` is returned. ``limit`` defaults to 20 and is hard-capped at
    100 to keep responses small enough for an LLM context window.

    Each result is the full app record (same shape as ``get_app``); use
    ``get_app`` directly when you already know the exact slug.
    """
    limit = max(1, min(limit, 100))
    pattern = f"%{query}%"
    async with get_session_maker()() as session:
        rows = (
            await session.scalars(
                select(AppRow)
                .where(
                    or_(
                        AppRow.slug.ilike(pattern),
                        AppRow.name.ilike(pattern),
                        AppRow.vendor.ilike(pattern),
                        AppRow.bundle_id.ilike(pattern),
                    )
                )
                .order_by(AppRow.slug)
                .limit(limit)
            )
        ).all()

    return [_serialize_app(row) for row in rows]


@mcp.tool
async def get_app(slug: str) -> dict:
    """
    Fetch a single app record by its slug.

    Returns the full app projection: identity (slug, name, vendor,
    bundle_id), versioning (current_version, latest_release_date),
    download metadata (download_url, install_method, sha256), and
    provenance (sources, cves). Identical to ``GET /apps/{slug}`` on
    the REST API.

    ``slug`` is the URL-friendly app identifier (e.g. "firefox",
    "1password8"); use ``search_apps`` first if you don't know the
    exact slug. Raises ``ValueError`` if no app with that slug exists
    in the catalog.
    """
    async with get_session_maker()() as session:
        row = await session.scalar(select(AppRow).where(AppRow.slug == slug))

    if row is None:
        raise ValueError(f"App with slug '{slug}' not found")

    return _serialize_app(row)


@mcp.tool
async def list_drift(
    vendor: str | None = None,
    source: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """
    Find apps where Patcher's upstream sources disagree on the latest version.

    Drift answers a question the stitched catalog is uniquely positioned to
    answer: *do upstream sources agree on what "latest" means?* When they
    don't, one source is usually silently stuck (vendor moved their release
    artifact, the label still finds the old location, and the source keeps
    reporting the old version indefinitely). Only sources that expose a
    stable per-app version string participate, currently Installomator and
    Homebrew Cask.

    ``vendor`` is an optional case-insensitive vendor filter (e.g. "Mozilla");
    None disables. ``source`` optionally narrows results to drift entries
    where the named source participated in the disagreement; None disables.
    ``limit`` defaults to 25 and is hard-capped at 100; ``offset`` defaults
    to 0.

    Returned dict has ``total_scanned`` (apps inspected, those with at
    least two versioned sources), ``total_with_drift`` (subset where
    sources disagreed, pre-pagination), and ``entries`` (the paged list of
    :class:`patcher_api.schemas.drift.DriftEntry` dicts).
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    async with get_session_maker()() as session:
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
    ).model_dump(mode="json")


@mcp.tool
async def list_categories() -> dict:
    """
    Return the catalog's distinct categorical values.

    Useful for an MCP client that wants to describe the catalog's shape
    (which install methods are represented, which sources have data, which
    vendors are present) without iterating every app. ``install_methods``
    is the static :class:`InstallMethod` enum (the universe of values
    Patcher recognizes, not just those currently in use); ``sources`` and
    ``vendors`` reflect what's actually in the catalog right now.

    Returned dict has keys ``install_methods`` (list[str]), ``sources``
    (list[str], sorted), and ``vendors`` (list[str], sorted).
    """
    async with get_session_maker()() as session:
        # Distinct sources: union the per-app ``sources`` arrays in Python.
        # SQLite's json_each could do this in SQL but the catalog is small
        # enough that the Python set is clearer and just as fast.
        all_source_arrays = (await session.scalars(select(AppRow.sources))).all()
        sources = sorted({src for arr in all_source_arrays for src in (arr or [])})

        vendor_rows = (
            await session.scalars(
                select(AppRow.vendor).where(AppRow.vendor.is_not(None)).distinct()
            )
        ).all()
        vendors = sorted(vendor_rows)

    return {
        "install_methods": [m.value for m in InstallMethod],
        "sources": sources,
        "vendors": vendors,
    }
