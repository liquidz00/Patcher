"""
Stitch the catalog — join Installomator labels and Homebrew Cask records
into unified ``apps`` rows.

Match strategies (in order, both exact):

1. Installomator label name == Cask token
2. Installomator display_name + ``.app`` == Cask artifact ``.app[0]``

Phase 1 walks every Installomator label, finds (or doesn't) a matching Cask,
and upserts an ``apps`` row keyed on slug = label name. Matched Cask tokens
are tracked. Phase 2 walks the remaining Cask records (those not claimed by
phase 1) and creates Cask-only ``apps`` rows keyed on slug = Cask token.

Per-row commits + try/except keep one problematic record from poisoning the
whole batch — same resilience pattern as the ingest scripts.

Idempotent — re-running upserts existing rows rather than duplicating.
"""

import logging
import re
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.core.installomator import is_shell_expression, looks_like_clean_http_url
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.models.jamf_app_installers import JamfAppInstaller
from patcher_api.models.mas import MasApp

log = logging.getLogger(__name__)

# Mirrors patcher_api.schemas.app.InstallMethod values. Anything outside this
# set comes back as None, which the nullable install_method column accepts.
_VALID_INSTALL_METHODS: set[str] = {
    "dmg",
    "pkg",
    "zip",
    "tbz",
    "pkgInDmg",
    "pkgInZip",
    "appInDmgInZip",
}

# Common reverse-DNS prefixes that aren't the vendor name itself. When
# packageID starts with one of these we skip to the next segment.
_REVERSE_DNS_TLDS: set[str] = {"com", "org", "net", "io", "co", "us", "edu", "app"}


def _extract_vendor(il: InstallomatorLabel) -> str | None:
    """
    Best-effort vendor extraction. Try reverse-DNS first
    (``com.mozilla.firefox`` → ``Mozilla``), fall back to first word of
    display_name, return None if neither yields anything.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :return: Vendor name, or None when no signal is available.
    :rtype: str | None
    """
    if il.package_id and "." in il.package_id:
        parts = il.package_id.split(".")
        if len(parts) >= 2:
            if parts[0].lower() in _REVERSE_DNS_TLDS:
                return parts[1][:1].upper() + parts[1][1:]
            return parts[0][:1].upper() + parts[0][1:]

    if il.display_name:
        return il.display_name.split()[0]

    return None


def _resolve_version(il: InstallomatorLabel, cask: HomebrewCask | None) -> str | None:
    """
    Prefer the literal label version; fall back to Cask version when the
    label's ``appNewVersion`` is a shell expression we haven't evaluated.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :param cask: Matched Cask row, if any.
    :type cask: :class:`HomebrewCask` | None
    :return: Version string, or None if neither side has a literal value.
    :rtype: str | None
    """
    if il.app_new_version and not is_shell_expression(il.app_new_version):
        return il.app_new_version
    if cask and cask.version:
        return cask.version
    return None


def _clean_cask_url(cask: HomebrewCask | None) -> str | None:
    """
    Return ``cask.url`` if it passes :func:`looks_like_clean_http_url`,
    otherwise ``None``.

    Used wherever stitch propagates a Cask URL into the apps table, both
    the phase 1 fallback (label URL missing or garbage) and the phase 2
    direct insert (Cask-only apps with no matching label). Centralizing
    here keeps the two paths from drifting: any new column-level URL
    constraint added in the future applies to both at once.

    :param cask: Cask row, or None.
    :type cask: :class:`HomebrewCask` | None
    :return: Clean http(s) URL, or None.
    :rtype: str | None
    """
    if cask is None or not cask.url:
        return None
    if not looks_like_clean_http_url(cask.url):
        return None
    return cask.url


def _resolve_download_url(il: InstallomatorLabel, cask: HomebrewCask | None) -> str | None:
    """
    Prefer the literal label download URL; fall back to Cask URL when the
    label's value is a shell expression or fails URL sanity checks.

    Both candidates are run through :func:`looks_like_clean_http_url` before
    being returned. This is defense in depth against ingest having stored
    garbage (HTML bodies, multi-line concats, ``ftp://``) into either
    source table. Ingest already validates on the way in; this second
    gate ensures the apps table can't inherit a value the API can't
    serialize as ``HttpUrl``.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :param cask: Matched Cask row, if any.
    :type cask: :class:`HomebrewCask` | None
    :return: Download URL string, or None if neither side has a usable value.
    :rtype: str | None
    """
    if (
        il.download_url
        and not is_shell_expression(il.download_url)
        and looks_like_clean_http_url(il.download_url)
    ):
        return il.download_url
    return _clean_cask_url(cask)


def _resolve_install_method(install_type: str | None) -> str | None:
    """
    Map an Installomator ``type`` value to our ``InstallMethod`` enum.
    Unknown types (or None) return None.
    """
    if install_type in _VALID_INSTALL_METHODS:
        return install_type
    return None


def _infer_install_method_from_cask(cask: HomebrewCask) -> str | None:
    """For Cask-only records, infer install method from the download URL extension."""
    if not cask.url:
        return None
    url_lower = cask.url.lower()
    if url_lower.endswith(".dmg"):
        return "dmg"
    if url_lower.endswith(".pkg"):
        return "pkg"
    if url_lower.endswith(".zip"):
        return "zip"
    if url_lower.endswith(".tbz") or url_lower.endswith(".tar.bz2"):
        return "tbz"
    return None


def _index_casks_by_app_name(casks: list[HomebrewCask]) -> dict[str, HomebrewCask]:
    """
    Build a lookup: ``Cask artifact .app[0]`` → Cask.

    Walks every artifact in every Cask. First Cask to claim a given .app
    name wins; later collisions are ignored.
    """
    index: dict[str, HomebrewCask] = {}
    for cask in casks:
        artifacts = cask.raw.get("artifacts") or []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            app_list = artifact.get("app")
            if isinstance(app_list, list) and app_list:
                first = app_list[0]
                if isinstance(first, str):
                    index.setdefault(first, cask)
    return index


def _find_matching_cask(
    il: InstallomatorLabel,
    casks_by_token: dict[str, HomebrewCask],
    casks_by_app_name: dict[str, HomebrewCask],
) -> HomebrewCask | None:
    """
    Try the two match strategies in order. First one to hit wins.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :param casks_by_token: Lookup from Cask token to Cask row.
    :type casks_by_token: dict[str, :class:`HomebrewCask`]
    :param casks_by_app_name: Lookup from artifact .app filename to Cask row.
    :type casks_by_app_name: dict[str, :class:`HomebrewCask`]
    :return: Matching Cask row, or None.
    :rtype: :class:`HomebrewCask` | None
    """
    if il.name in casks_by_token:
        return casks_by_token[il.name]
    if il.display_name:
        candidate = f"{il.display_name}.app"
        if candidate in casks_by_app_name:
            return casks_by_app_name[candidate]
    return None


def _build_installomator_payload(il: InstallomatorLabel) -> dict[str, Any]:
    """
    Build the InstallomatorSource shape for the source_detail JSON column.
    """
    return {
        "label_name": il.name,
        "label_url": (
            f"https://github.com/Installomator/Installomator/blob/main/fragments/labels/{il.name}.sh"
        ),
        "raw": il.raw,
    }


def _build_cask_payload(cask: HomebrewCask) -> dict[str, Any]:
    """
    Build the HomebrewCaskSource shape for the source_detail JSON column.
    """
    return {
        "token": cask.token,
        "cask_json": cask.raw,
    }


_CANONICAL_SOURCE_ORDER = (
    "installomator",
    "homebrew_cask",
    "autopkg",
    "jamf_app_installer",
    "mas",
)


def _canonicalize_sources(sources: list[str]) -> list[str]:
    """Reorder a sources list into the canonical fixed-position ordering."""
    present = set(sources)
    return [s for s in _CANONICAL_SOURCE_ORDER if s in present]


def _build_mas_payload(mas_app: MasApp) -> dict[str, Any]:
    """
    Build the MasSource shape for the source_detail JSON column.

    The full Apple lookup payload is preserved in ``raw`` so consumers can
    see Apple's native shape (matching the principle applied to Cask and
    Installomator sources).
    """
    return {
        "bundle_id": mas_app.bundle_id,
        "store_url": mas_app.store_url,
        "raw": mas_app.raw,
    }


def _build_autopkg_payload(recipes: list[AutopkgRecipe]) -> dict[str, Any]:
    """
    Build the AutopkgSource shape (a list of recipe entries) for the
    source_detail JSON column.

    A single app typically has multiple AutoPkg recipes (download, munki,
    pkg, jamf, etc.) across one or more maintainer repos. Each match is
    preserved as a separate entry. ``recipe_url`` is constructed from the
    repo + path; GitHub redirects ``/blob/master/`` to ``/blob/main/``
    automatically for repos that renamed the default branch.
    """
    return {
        "recipes": [
            {
                "identifier": r.identifier,
                "name": r.name,
                "shortname": r.shortname,
                "repo": r.repo,
                "path": r.path,
                "parent_identifier": r.parent_identifier,
                "inferred_type": r.inferred_type,
                "recipe_url": f"https://github.com/{r.repo}/blob/master/{r.path}",
            }
            for r in recipes
        ],
    }


def _normalize_name(name: str | None) -> str:
    """
    Lowercase + strip all non-alphanumeric for cross-variant name matching.

    AutoPkg recipe names use both whitespace-separated (``"Google Chrome"``)
    and concatenated (``"GoogleChrome"``) forms for the same app, depending
    on the maintainer. Both normalize to ``"googlechrome"`` so either
    variant matches an app whose display name is the other variant. Empty
    or ``None`` input returns the empty string, which won't match anything
    in the index (lookups against empty keys are guarded at the call site).
    """
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _index_autopkg_by_name(recipes: list[AutopkgRecipe]) -> dict[str, list[AutopkgRecipe]]:
    """
    Build a normalized-name → list[recipe] lookup over all AutoPkg recipes.

    Multiple recipes per name is the common case: Firefox alone usually
    has 5 to 10 child recipes across different maintainer repos. The
    list ordering is stable across runs since SQL ordering is preserved
    through the upstream iteration.
    """
    index: dict[str, list[AutopkgRecipe]] = {}
    for r in recipes:
        key = _normalize_name(r.name)
        if not key:
            continue
        index.setdefault(key, []).append(r)
    return index


def _build_jai_payload(jai: JamfAppInstaller) -> dict[str, Any]:
    """
    Build the JamfAppInstallerSource shape for the source_detail JSON column.

    Mirrors the public HTML catalog's three columns. When the unlisted
    Jamf Pro API endpoint becomes available, this helper grows additional
    fields (bundle_id, version, download URL, Jamf Software Title ID).
    """
    return {
        "title": jai.title,
        "source": jai.source,
        "host": jai.host,
    }


async def _attach_mas_to_existing_app(
    session: AsyncSession,
    *,
    app_id: int,
    mas_app: MasApp,
) -> None:
    """
    Merge a MAS payload into an existing ``apps`` row instead of creating a
    new MAS-only row.

    Invoked by phase 3 when ``_slugify(mas_app.name)`` collides with an
    already-stitched row (typically a phase-2 Cask-only app whose token
    happens to match the MAS app's slugified name — Apple Pro Suite +
    Microsoft Office are the common cases). The merge preserves the
    existing row's name/vendor/version/download_url and only:

    1. Appends ``"mas"`` to the row's ``sources`` list, reordered into the
       canonical fixed-position sequence.
    2. Writes the mas source_detail payload (existing detail row gets its
       ``mas`` column updated; if no detail row exists for any reason, one
       is created via ON CONFLICT DO UPDATE).
    """
    current_sources = (
        await session.scalar(select(AppRow.sources).where(AppRow.id == app_id))
    ) or []
    new_sources = _canonicalize_sources([*current_sources, "mas"])
    await session.execute(update(AppRow).where(AppRow.id == app_id).values(sources=new_sources))

    mas_payload = _build_mas_payload(mas_app)
    detail_stmt = sqlite_insert(AppSourceDetailRow).values(
        app_id=app_id,
        installomator=None,
        homebrew_cask=None,
        autopkg=None,
        mas=mas_payload,
        jamf_app_installer=None,
    )
    detail_stmt = detail_stmt.on_conflict_do_update(
        index_elements=["app_id"],
        set_={"mas": detail_stmt.excluded.mas},
    )
    await session.execute(detail_stmt)


def _index_jai_by_title(jai_rows: list[JamfAppInstaller]) -> dict[str, JamfAppInstaller]:
    """
    Build a normalized-title → JAI row lookup. Titles are unique in the
    JAI catalog, so this is a 1:1 map rather than the 1:N pattern AutoPkg
    uses.
    """
    index: dict[str, JamfAppInstaller] = {}
    for j in jai_rows:
        key = _normalize_name(j.title)
        if not key:
            continue
        # First-write wins on collision (shouldn't happen in practice with
        # unique upstream titles, but defensive).
        index.setdefault(key, j)
    return index


def _slugify(name: str) -> str:
    """
    Convert an app name to a URL-friendly slug.

    Lowercase, collapse runs of non-alphanumeric into single hyphens,
    strip leading and trailing hyphens. Used for MAS-only apps that don't
    inherit a slug from Installomator (which uses the label name) or
    Homebrew Cask (which uses the cask token).

    Returns ``"unknown"`` on inputs that collapse to empty, so callers
    don't have to guard against empty-string slugs blowing up the
    unique-index constraint.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return cleaned or "unknown"


async def _upsert_app_with_sources(
    session: AsyncSession,
    *,
    slug: str,
    bundle_id: str | None,
    name: str,
    vendor: str | None,
    current_version: str | None,
    download_url: str | None,
    install_method: str | None,
    sha256: str | None,
    sources: list[str],
    installomator_payload: dict | None,
    homebrew_payload: dict | None,
    autopkg_payload: dict | None,
    mas_payload: dict | None,
    jamf_app_installer_payload: dict | None,
) -> None:
    """
    Upsert an ``apps`` row by slug, then upsert its ``app_source_details`` row
    by ``app_id``. Both operations land in a single commit at the end so the
    pair stays consistent.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param slug: URL-friendly identifier; primary upsert key.
    :type slug: str
    :param bundle_id: Reverse-DNS bundle identifier, or None.
    :type bundle_id: str | None
    :param name: Human-readable name (required).
    :type name: str
    :param vendor: Publisher; best-effort, may be None.
    :type vendor: str | None
    :param current_version: Latest known version string; None if unresolved.
    :type current_version: str | None
    :param download_url: Direct download URL; None if unresolved.
    :type download_url: str | None
    :param install_method: One of the InstallMethod enum values, or None.
    :type install_method: str | None
    :param sha256: SHA-256 of the artifact, or None.
    :type sha256: str | None
    :param sources: List of source names (e.g. ``["installomator", "homebrew_cask"]``).
    :type sources: list[str]
    :param installomator_payload: InstallomatorSource shape, or None.
    :type installomator_payload: dict | None
    :param homebrew_payload: HomebrewCaskSource shape, or None.
    :type homebrew_payload: dict | None
    :param autopkg_payload: AutopkgSource shape, or None.
    :type autopkg_payload: dict | None
    :param mas_payload: MasSource shape, or None.
    :type mas_payload: dict | None
    :param jamf_app_installer_payload: JamfAppInstallerSource shape, or None.
    :type jamf_app_installer_payload: dict | None
    """
    apps_stmt = sqlite_insert(AppRow).values(
        slug=slug,
        bundle_id=bundle_id,
        name=name,
        vendor=vendor,
        current_version=current_version,
        latest_release_date=None,
        download_url=download_url,
        install_method=install_method,
        sha256=sha256,
        sources=sources,
        cves=[],
    )
    apps_stmt = apps_stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "bundle_id": apps_stmt.excluded.bundle_id,
            "name": apps_stmt.excluded.name,
            "vendor": apps_stmt.excluded.vendor,
            "current_version": apps_stmt.excluded.current_version,
            "download_url": apps_stmt.excluded.download_url,
            "install_method": apps_stmt.excluded.install_method,
            "sha256": apps_stmt.excluded.sha256,
            "sources": apps_stmt.excluded.sources,
        },
    )
    await session.execute(apps_stmt)

    # Separate SELECT to get the row's id. Avoids using RETURNING with ON CONFLICT,
    # which is broken in SQLite < 3.45 (Python 3.11 ships 3.39, Python 3.12 ships 3.42).
    # The fix landed in SQLite 3.45.0 (Python 3.13+).
    app_id = await session.scalar(select(AppRow.id).where(AppRow.slug == slug))

    detail_stmt = sqlite_insert(AppSourceDetailRow).values(
        app_id=app_id,
        installomator=installomator_payload,
        homebrew_cask=homebrew_payload,
        autopkg=autopkg_payload,
        mas=mas_payload,
        jamf_app_installer=jamf_app_installer_payload,
    )
    detail_stmt = detail_stmt.on_conflict_do_update(
        index_elements=["app_id"],
        set_={
            "installomator": detail_stmt.excluded.installomator,
            "homebrew_cask": detail_stmt.excluded.homebrew_cask,
            "autopkg": detail_stmt.excluded.autopkg,
            "mas": detail_stmt.excluded.mas,
            "jamf_app_installer": detail_stmt.excluded.jamf_app_installer,
        },
    )
    await session.execute(detail_stmt)


async def stitch_catalog(session: AsyncSession) -> tuple[int, int, int, int, int, int, int, int]:
    """
    Run the stitch process. Builds unified ``apps`` rows from ingested
    Installomator labels, Homebrew Cask records, Mac App Store metadata,
    AutoPkg recipe-index entries, and Jamf App Installers catalog rows.

    Phases:

    1. **Installomator-led.** For each label, try to match a Cask (token or
       artifact app-name), a MAS record (by ``packageID``), any AutoPkg
       recipes (by normalized display name), and any JAI catalog row (by
       normalized display name). Upsert one ``apps`` row per label.
       Sources land in canonical ordering
       ``[installomator, homebrew_cask, autopkg, jamf_app_installer, mas]``
       regardless of which combination is present.
    2. **Cask-only.** Walk Casks not claimed in phase 1. Cask records don't
       expose ``bundle_id``, so no MAS join is attempted, but AutoPkg + JAI
       name matching is still attempted.
    3. **MAS-only with merge-on-collision.** Walk MAS records not joined in
       phase 1. Slug derived from MAS ``trackName`` via :func:`_slugify`. If
       the slug collides with an existing phase-1 or phase-2 row, merge the
       MAS payload into that row via :func:`_attach_mas_to_existing_app`
       rather than skipping (Microsoft Office + Apple Pro Suite are typical
       collision cases). Otherwise create a new MAS-only row. AutoPkg + JAI
       name matching still applies for newly-created rows.

    **AutoPkg and JAI never create new apps.** Both are coverage indicators
    attached to existing apps when their normalized name matches the app's
    display name.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :return: ``(installomator_apps, cask_only_apps, both_sources,
        mas_only_apps, mas_merged_apps, autopkg_attached_apps,
        jai_attached_apps, failed)``.

        - ``installomator_apps`` is the count of apps with an Installomator source
        - ``cask_only_apps`` is the count of apps with only a Cask source
        - ``both_sources`` is the subset of ``installomator_apps`` that also matched a Cask
        - ``mas_only_apps`` is the count of *newly-created* MAS-only rows from phase 3
        - ``mas_merged_apps`` is the count of MAS records merged into an existing
          row via slug collision in phase 3
        - ``autopkg_attached_apps`` is the count of apps with one or more
          AutoPkg recipes attached (across all phases)
        - ``jai_attached_apps`` is the count of apps with a JAI catalog row
          attached (across all phases)
        - ``failed`` is the count of records that raised an unexpected error
    :rtype: tuple[int, int, int, int, int, int, int, int]
    """
    labels = (await session.scalars(select(InstallomatorLabel))).all()
    casks = (await session.scalars(select(HomebrewCask))).all()
    mas_apps = (await session.scalars(select(MasApp))).all()
    autopkg_recipes = (await session.scalars(select(AutopkgRecipe))).all()
    jai_rows = (await session.scalars(select(JamfAppInstaller))).all()

    casks_by_token = {c.token: c for c in casks}
    casks_by_app_name = _index_casks_by_app_name(casks)
    mas_by_bundle_id = {m.bundle_id: m for m in mas_apps}
    autopkg_by_name = _index_autopkg_by_name(list(autopkg_recipes))
    jai_by_title = _index_jai_by_title(list(jai_rows))
    matched_cask_tokens: set[str] = set()
    matched_mas_bundle_ids: set[str] = set()

    installomator_count = 0
    both_sources = 0
    autopkg_attached_count = 0
    jai_attached_count = 0
    mas_merged_count = 0
    failed = 0

    for il in labels:
        matching_cask = _find_matching_cask(il, casks_by_token, casks_by_app_name)
        matching_mas = mas_by_bundle_id.get(il.package_id) if il.package_id else None
        display_name = il.display_name or il.name
        normalized = _normalize_name(display_name)
        matching_autopkg = autopkg_by_name.get(normalized, [])
        matching_jai = jai_by_title.get(normalized)

        sources = ["installomator"]
        if matching_cask is not None:
            sources.append("homebrew_cask")
        if matching_autopkg:
            sources.append("autopkg")
        if matching_jai is not None:
            sources.append("jamf_app_installer")
        if matching_mas is not None:
            sources.append("mas")

        try:
            async with session.begin_nested():
                await _upsert_app_with_sources(
                    session,
                    slug=il.name,
                    bundle_id=il.package_id,
                    name=display_name,
                    vendor=_extract_vendor(il),
                    current_version=_resolve_version(il, matching_cask),
                    download_url=_resolve_download_url(il, matching_cask),
                    install_method=_resolve_install_method(il.install_type),
                    sha256=matching_cask.sha256 if matching_cask else None,
                    sources=sources,
                    installomator_payload=_build_installomator_payload(il),
                    homebrew_payload=_build_cask_payload(matching_cask) if matching_cask else None,
                    autopkg_payload=(
                        _build_autopkg_payload(matching_autopkg) if matching_autopkg else None
                    ),
                    mas_payload=_build_mas_payload(matching_mas) if matching_mas else None,
                    jamf_app_installer_payload=(
                        _build_jai_payload(matching_jai) if matching_jai else None
                    ),
                )
            if matching_cask is not None:
                matched_cask_tokens.add(matching_cask.token)
                both_sources += 1
            if matching_mas is not None:
                matched_mas_bundle_ids.add(matching_mas.bundle_id)
            if matching_autopkg:
                autopkg_attached_count += 1
            if matching_jai is not None:
                jai_attached_count += 1
            installomator_count += 1
        except Exception as exc:
            log.warning("Failed to stitch Installomator label %r: %s", il.name, exc)
            failed += 1

    cask_only_count = 0
    for cask in casks:
        if cask.token in matched_cask_tokens:
            continue

        cask_name = cask.name or cask.token
        normalized = _normalize_name(cask_name)
        matching_autopkg = autopkg_by_name.get(normalized, [])
        matching_jai = jai_by_title.get(normalized)

        sources = ["homebrew_cask"]
        if matching_autopkg:
            sources.append("autopkg")
        if matching_jai is not None:
            sources.append("jamf_app_installer")

        try:
            async with session.begin_nested():
                await _upsert_app_with_sources(
                    session,
                    slug=cask.token,
                    bundle_id=None,
                    name=cask_name,
                    vendor=cask_name.split()[0] if cask_name else None,
                    current_version=cask.version,
                    download_url=_clean_cask_url(cask),
                    install_method=_infer_install_method_from_cask(cask),
                    sha256=cask.sha256,
                    sources=sources,
                    installomator_payload=None,
                    homebrew_payload=_build_cask_payload(cask),
                    autopkg_payload=(
                        _build_autopkg_payload(matching_autopkg) if matching_autopkg else None
                    ),
                    mas_payload=None,
                    jamf_app_installer_payload=(
                        _build_jai_payload(matching_jai) if matching_jai else None
                    ),
                )
            if matching_autopkg:
                autopkg_attached_count += 1
            if matching_jai is not None:
                jai_attached_count += 1
            cask_only_count += 1
        except Exception as exc:
            log.warning("Failed to stitch Cask %r: %s", cask.token, exc)
            failed += 1

    mas_only_count = 0
    for mas_app in mas_apps:
        if mas_app.bundle_id in matched_mas_bundle_ids:
            continue

        slug = _slugify(mas_app.name)
        # If the slugified MAS name already exists on the apps table (typically
        # because a phase-2 Cask-only app claimed it first — Apple Pro Suite +
        # Microsoft Office are the common cases), merge the MAS payload into
        # the existing row instead of skipping or overwriting it. Preserves
        # name/vendor/version/download_url from the prior source; only adds
        # "mas" to sources and writes the mas source_detail.
        existing_app_id = await session.scalar(select(AppRow.id).where(AppRow.slug == slug))
        if existing_app_id is not None:
            try:
                async with session.begin_nested():
                    await _attach_mas_to_existing_app(
                        session, app_id=existing_app_id, mas_app=mas_app
                    )
                mas_merged_count += 1
            except Exception as exc:
                log.warning(
                    "Failed to merge MAS app %r into existing slug %r: %s",
                    mas_app.bundle_id,
                    slug,
                    exc,
                )
                failed += 1
            continue

        normalized = _normalize_name(mas_app.name)
        matching_autopkg = autopkg_by_name.get(normalized, [])
        matching_jai = jai_by_title.get(normalized)

        sources: list[str] = []
        if matching_autopkg:
            sources.append("autopkg")
        if matching_jai is not None:
            sources.append("jamf_app_installer")
        sources.append("mas")

        try:
            async with session.begin_nested():
                await _upsert_app_with_sources(
                    session,
                    slug=slug,
                    bundle_id=mas_app.bundle_id,
                    name=mas_app.name,
                    vendor=mas_app.raw.get("artistName"),
                    current_version=mas_app.version,
                    download_url=None,
                    install_method=None,
                    sha256=None,
                    sources=sources,
                    installomator_payload=None,
                    homebrew_payload=None,
                    autopkg_payload=(
                        _build_autopkg_payload(matching_autopkg) if matching_autopkg else None
                    ),
                    mas_payload=_build_mas_payload(mas_app),
                    jamf_app_installer_payload=(
                        _build_jai_payload(matching_jai) if matching_jai else None
                    ),
                )
            if matching_autopkg:
                autopkg_attached_count += 1
            if matching_jai is not None:
                jai_attached_count += 1
            mas_only_count += 1
        except Exception as exc:
            log.warning("Failed to stitch MAS app %r: %s", mas_app.bundle_id, exc)
            failed += 1

    await session.commit()

    # Invalidate the session's identity map. Every upsert above was a Core-level
    # ``sqlite_insert.on_conflict_do_update`` that bypasses the ORM, so any ORM
    # objects loaded before stitch ran (e.g. seed apps the caller already touched)
    # would otherwise return stale attribute values on next access.
    session.expire_all()

    return (
        installomator_count,
        cask_only_count,
        both_sources,
        mas_only_count,
        mas_merged_count,
        autopkg_attached_count,
        jai_attached_count,
        failed,
    )
