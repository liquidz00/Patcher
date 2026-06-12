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

from sqlalchemy import or_, select

from patcher.catalog import AppSources
from patcher_api.db import get_session_maker
from patcher_api.drift import scan_drift
from patcher_api.labels import build_installomator_label
from patcher_api.mcp._queries import catalog_categories, catalog_summary, serialize_app
from patcher_api.mcp.server import mcp
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow


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
        return await catalog_summary(session)


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

    return [serialize_app(row) for row in rows]


@mcp.tool
async def get_app(slug: str) -> dict:
    """
    Fetch a single app record by its slug.

    Returns the full app projection: identity (slug, name, vendor,
    bundle_id), versioning (current_version, latest_release_date),
    download metadata (download_url, install_method, sha256), and
    provenance (sources). Identical to ``GET /apps/{slug}`` on
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

    return serialize_app(row)


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

    return scan_drift(rows, source=source, limit=limit, offset=offset).model_dump(mode="json")


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
        return await catalog_categories(session)


@mcp.tool
async def generate_installomator_label(slug: str) -> dict:
    """
    Generate an Installomator-shaped label for the app identified by ``slug``.

    Projects the app's Homebrew Cask, Installomator, and Jamf App Installer
    source payloads into the Installomator label format that consumers can
    drop into their Installomator deployments. Mirrors the REST endpoint
    ``POST /apps/{slug}/generate-label`` exactly.

    ``slug`` is the URL-friendly app identifier (e.g. "firefox"); use
    ``search_apps`` first if you don't know the exact slug. Raises
    ``ValueError`` if no app with that slug exists, or if the app has no
    source detail attached (rare, usually a leftover seed record without
    upstream coverage).

    Returned dict has ``label_name`` (str, the app's slug), ``content`` (dict
    of Installomator variable name to value, with unresolved fields omitted),
    ``sources_used`` (list[str] naming which upstream sources contributed),
    and ``warnings`` (list[str] explaining any fields that couldn't be
    resolved, most commonly ``expectedTeamID`` for Cask-only apps).
    """
    async with get_session_maker()() as session:
        app_row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
        if app_row is None:
            raise ValueError(f"App with slug '{slug}' not found")

        detail = await session.scalar(
            select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
        )

        if detail is None or (
            detail.homebrew_cask is None
            and detail.installomator is None
            and detail.jamf_app_installer is None
        ):
            raise ValueError(
                f"App '{slug}' has no source detail, cannot generate a label. "
                "This is usually a leftover seed record; expected for production data."
            )

        return build_installomator_label(app_row, detail).model_dump(mode="json")


@mcp.tool
async def get_app_sources(slug: str) -> dict:
    """
    Return the raw per-source payloads for the app identified by ``slug``.

    Use this when the caller needs to inspect what each upstream source said
    about an app (the raw Installomator label dict, the full Homebrew Cask
    JSON, the Jamf App Installer catalog row), as opposed to the stitched
    canonical projection that ``get_app`` returns. Mirrors the REST endpoint
    ``GET /apps/{slug}/sources`` exactly.

    ``slug`` is the URL-friendly app identifier. Raises ``ValueError`` if no
    app with that slug exists. If the app exists but has no source detail
    row attached, returns a dict with every source key set to ``None``
    rather than raising.

    Returned dict has keys ``installomator``, ``homebrew_cask``, ``autopkg``,
    ``mas``, and ``jamf_app_installer``; each value is either the source's
    native payload (dict) or ``None`` when that source has no data for the app.
    """
    async with get_session_maker()() as session:
        app_row = await session.scalar(select(AppRow).where(AppRow.slug == slug))
        if app_row is None:
            raise ValueError(f"App with slug '{slug}' not found")

        detail_row = await session.scalar(
            select(AppSourceDetailRow).where(AppSourceDetailRow.app_id == app_row.id)
        )
        if detail_row is None:
            return AppSources().model_dump(mode="json")

        return AppSources.model_validate(
            {
                "installomator": detail_row.installomator,
                "homebrew_cask": detail_row.homebrew_cask,
                "autopkg": detail_row.autopkg,
                "jamf_app_installer": detail_row.jamf_app_installer,
            }
        ).model_dump(mode="json")


@mcp.tool
async def list_recent_changes(limit: int = 25) -> list[dict]:
    """
    Return the most recently added apps in the catalog, newest first.

    Ordering uses ``App.id`` descending as a proxy for recency: rows are
    autoincrement-assigned at ingest time, so a higher id means a later
    insertion. This is honest about what the catalog can currently express;
    once the ``App`` model grows a ``modified_at`` timestamp column, this
    tool should switch to that column and accept a ``since_iso`` filter
    parameter for true change-feed semantics.

    ``limit`` defaults to 25 and is hard-capped at 100 to keep responses
    small enough for an LLM context window.

    Each result is the full app record (same shape as ``get_app``).
    """
    limit = max(1, min(limit, 100))
    async with get_session_maker()() as session:
        rows = (await session.scalars(select(AppRow).order_by(AppRow.id.desc()).limit(limit))).all()

    return [serialize_app(row) for row in rows]
