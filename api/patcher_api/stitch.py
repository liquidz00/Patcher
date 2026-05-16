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
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.core.installomator import is_shell_expression, looks_like_clean_http_url
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel

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
    if cask and cask.url and looks_like_clean_http_url(cask.url):
        return cask.url
    return None


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
    )
    detail_stmt = detail_stmt.on_conflict_do_update(
        index_elements=["app_id"],
        set_={
            "installomator": detail_stmt.excluded.installomator,
            "homebrew_cask": detail_stmt.excluded.homebrew_cask,
            "autopkg": detail_stmt.excluded.autopkg,
        },
    )
    await session.execute(detail_stmt)


async def stitch_catalog(session: AsyncSession) -> tuple[int, int, int, int]:
    """
    Run the stitch process — build unified ``apps`` rows from ingested
    Installomator labels and Homebrew Cask records.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :return: ``(installomator_apps, cask_only_apps, both_sources, failed)``
        where:

        - ``installomator_apps`` — count of apps with an Installomator source
        - ``cask_only_apps`` — count of apps with only a Cask source
        - ``both_sources`` — subset of ``installomator_apps`` that also matched a Cask
        - ``failed`` — count of records that raised an unexpected error
    :rtype: tuple[int, int, int, int]
    """
    labels = (await session.scalars(select(InstallomatorLabel))).all()
    casks = (await session.scalars(select(HomebrewCask))).all()

    casks_by_token = {c.token: c for c in casks}
    casks_by_app_name = _index_casks_by_app_name(casks)
    matched_cask_tokens: set[str] = set()

    installomator_count = 0
    both_sources = 0
    failed = 0

    for il in labels:
        matching_cask = _find_matching_cask(il, casks_by_token, casks_by_app_name)

        try:
            async with session.begin_nested():
                await _upsert_app_with_sources(
                    session,
                    slug=il.name,
                    bundle_id=il.package_id,
                    name=il.display_name or il.name,
                    vendor=_extract_vendor(il),
                    current_version=_resolve_version(il, matching_cask),
                    download_url=_resolve_download_url(il, matching_cask),
                    install_method=_resolve_install_method(il.install_type),
                    sha256=matching_cask.sha256 if matching_cask else None,
                    sources=(
                        ["installomator", "homebrew_cask"] if matching_cask else ["installomator"]
                    ),
                    installomator_payload=_build_installomator_payload(il),
                    homebrew_payload=_build_cask_payload(matching_cask) if matching_cask else None,
                    autopkg_payload=None,
                )
            if matching_cask is not None:
                matched_cask_tokens.add(matching_cask.token)
                both_sources += 1
            installomator_count += 1
        except Exception as exc:
            log.warning("Failed to stitch Installomator label %r: %s", il.name, exc)
            failed += 1

    cask_only_count = 0
    for cask in casks:
        if cask.token in matched_cask_tokens:
            continue

        cask_name = cask.name or cask.token
        try:
            async with session.begin_nested():
                await _upsert_app_with_sources(
                    session,
                    slug=cask.token,
                    bundle_id=None,
                    name=cask_name,
                    vendor=cask_name.split()[0] if cask_name else None,
                    current_version=cask.version,
                    download_url=cask.url,
                    install_method=_infer_install_method_from_cask(cask),
                    sha256=cask.sha256,
                    sources=["homebrew_cask"],
                    installomator_payload=None,
                    homebrew_payload=_build_cask_payload(cask),
                    autopkg_payload=None,
                )
            cask_only_count += 1
        except Exception as exc:
            log.warning("Failed to stitch Cask %r: %s", cask.token, exc)
            failed += 1

    await session.commit()

    # Invalidate the session's identity map — every upsert above was a Core-level
    # ``sqlite_insert.on_conflict_do_update`` that bypasses the ORM, so any ORM
    # objects loaded before stitch ran (e.g. seed apps the caller already touched)
    # would otherwise return stale attribute values on next access.
    session.expire_all()

    return installomator_count, cask_only_count, both_sources, failed
