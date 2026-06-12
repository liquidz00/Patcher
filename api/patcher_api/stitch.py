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
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher.catalog._normalize import normalize_name as _normalize_name
from patcher.policy import CURATED_BUNDLE_IDS
from patcher_api.installomator.resolver import is_shell_expression, looks_like_clean_http_url
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.models.autopkg import AutopkgRecipe
from patcher_api.models.homebrew import HomebrewCask
from patcher_api.models.installomator import InstallomatorLabel
from patcher_api.models.jamf import JamfAppInstaller

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

# Canonical ordering for the apps.sources list.
_CANONICAL_SOURCE_ORDER = (
    "installomator",
    "homebrew_cask",
    "autopkg",
    "jamf_app_installer",
)

# JAI titles carry decoration the label name omits (trailing version/edition, leading vendor); strip it so they match.
_JAI_YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
_JAI_VERSION_PATTERN = re.compile(r"^v?\d+(?:\.\d+)*$")
_JAI_EDITION_TOKENS: set[str] = {
    "dc",
    "continuous",
    "x",
    "pro",
    "enterprise",
    "standard",
    "lts",
    "ce",
    "beta",
    "unified",
    "classic",
    "legacy",
    "app",
    "edition",
    "plus",
    "mac",
    "macos",
}
# Strip a leading token only when it's a known vendor, so two-word names ("Visual Studio") keep their first word.
_JAI_VENDOR_PREFIXES: set[str] = {
    "adobe",
    "amazon",
    "apple",
    "atlassian",
    "cisco",
    "citrix",
    "dell",
    "extensis",
    "facebook",
    "google",
    "hp",
    "ibm",
    "iterate",
    "jamf",
    "jetbrains",
    "logmein",
    "microsoft",
    "mozilla",
    "openai",
    "oracle",
    "poly",
    "readcube",
    "root3",
    "sap",
    "techsmith",
    "vmware",
    "zoom",
}


@dataclass(frozen=True)
class _StitchIndexes:
    """The five lookups both stitch phases match against, built once from the ingested rows."""

    casks_by_token: dict[str, HomebrewCask]
    casks_by_app_name: dict[str, HomebrewCask]
    autopkg_by_name: dict[str, list[AutopkgRecipe]]
    jai_by_title: dict[str, JamfAppInstaller]
    jai_by_bundle_id: dict[str, JamfAppInstaller]

    @classmethod
    def build(
        cls,
        casks: list[HomebrewCask],
        autopkg_recipes: list[AutopkgRecipe],
        jai_rows: list[JamfAppInstaller],
    ) -> "_StitchIndexes":
        """Construct every lookup from the ingested source rows."""
        return cls(
            casks_by_token={c.token: c for c in casks},
            casks_by_app_name=_index_casks_by_app_name(casks),
            autopkg_by_name=_index_autopkg_by_name(autopkg_recipes),
            jai_by_title=_index_jai_by_title(jai_rows),
            jai_by_bundle_id={j.bundle_id: j for j in jai_rows if j.bundle_id},
        )


@dataclass
class _ResolvedApp:
    """One app's fully-resolved upsert payload plus the flags the phase loops tally."""

    upsert_kwargs: dict[str, Any]
    matched_cask_token: str | None
    has_autopkg: bool
    has_jai: bool


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


def _resolve_version(
    il: InstallomatorLabel,
    cask: HomebrewCask | None,
    jai: JamfAppInstaller | None = None,
) -> str | None:
    """
    Prefer the literal label version; fall back to Cask version when the
    label's ``appNewVersion`` is a shell expression we haven't evaluated; last
    resort, JAI's catalog version when both upstream sources are silent.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :param cask: Matched Cask row, if any.
    :type cask: :class:`HomebrewCask` | None
    :param jai: Matched JAI catalog row, if any.
    :type jai: :class:`JamfAppInstaller` | None
    :return: Version string, or None if no source has a literal value.
    :rtype: str | None
    """
    if il.app_new_version and not is_shell_expression(il.app_new_version):
        return il.app_new_version
    if cask and cask.version:
        return cask.version
    if jai and jai.version:
        return jai.version
    return None


def _jai_external_url(jai: JamfAppInstaller | None) -> str | None:
    """
    JAI's ``download_url`` only when it's the vendor's direct URL.

    Jamf-hosted titles (``source = "Jamf"``) point at
    ``appinstallers-packages.services.jamfcloud.com``, which is signed by Jamf
    (Team ID ``483DWKW443``) rather than the vendor — useless to Installomator,
    which validates against the actual app developer's Team ID. Only
    ``source = "External"`` titles carry the vendor's URL we actually want.
    """
    if jai is None or not jai.download_url or jai.source != "External":
        return None
    if not looks_like_clean_http_url(jai.download_url):
        return None
    return jai.download_url


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


def _resolve_download_url(
    il: InstallomatorLabel,
    cask: HomebrewCask | None,
    jai: JamfAppInstaller | None = None,
) -> str | None:
    """
    Prefer the literal label download URL; fall back to Cask URL, then JAI's
    vendor URL when both upstreams are silent.

    Every candidate is run through :func:`looks_like_clean_http_url` before
    being returned. This is defense in depth against ingest having stored
    garbage (HTML bodies, multi-line concats, ``ftp://``) into any source.
    Ingest already validates on the way in; this second gate ensures the apps
    table can't inherit a value the API can't serialize as ``HttpUrl``.

    :param il: Installomator label row.
    :type il: :class:`InstallomatorLabel`
    :param cask: Matched Cask row, if any.
    :type cask: :class:`HomebrewCask` | None
    :param jai: Matched JAI catalog row, if any.
    :type jai: :class:`JamfAppInstaller` | None
    :return: Download URL string, or None if no source has a usable value.
    :rtype: str | None
    """
    if (
        il.download_url
        and not is_shell_expression(il.download_url)
        and looks_like_clean_http_url(il.download_url)
    ):
        return il.download_url
    return _clean_cask_url(cask) or _jai_external_url(jai)


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


def _canonicalize_sources(sources: list[str]) -> list[str]:
    """Reorder a sources list into the canonical fixed-position ordering."""
    present = set(sources)
    return [s for s in _CANONICAL_SOURCE_ORDER if s in present]


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

    Carries the HTML columns plus the titles-API enrichment (``None`` on
    HTML-only rows).
    """
    return {
        "title": jai.title,
        "source": jai.source,
        "host": jai.host,
        "bundle_id": jai.bundle_id,
        "version": jai.version,
        "jamf_id": jai.jamf_id,
        "download_url": jai.download_url,
        "architecture": jai.architecture,
    }


def _jai_index_keys(title: str) -> list[str]:
    """
    Normalized lookup keys a JAI title should be indexed under, decoration
    widening down the list so exact forms keep priority:

    1. the exact normalized title (``"SAP Privileges"`` → ``"sapprivileges"``),
    2. with trailing version/year/edition tokens dropped
       (``"Sublime Text 4"`` → ``"sublimetext"``), and
    3. additionally with a leading *known-vendor* token dropped
       (``"SAP Privileges"`` → ``"privileges"``).

    The vendor strip is gated on :data:`_JAI_VENDOR_PREFIXES` so a real
    two-word app name never loses its first word. Bare-string keys only —
    callers map each to the row and resolve collisions first-wins.
    """
    exact = _normalize_name(title)
    keys = [exact] if exact else []

    tokens = re.findall(r"[a-z0-9]+", title.lower())
    while tokens and (
        _JAI_YEAR_PATTERN.match(tokens[-1])
        or tokens[-1] in _JAI_EDITION_TOKENS
        or _JAI_VERSION_PATTERN.fullmatch(tokens[-1])
    ):
        tokens.pop()

    trailing_stripped = "".join(tokens)
    if trailing_stripped and trailing_stripped not in keys:
        keys.append(trailing_stripped)
    if tokens and tokens[0] in _JAI_VENDOR_PREFIXES:
        vendor_stripped = "".join(tokens[1:])
        if vendor_stripped and vendor_stripped not in keys:
            keys.append(vendor_stripped)
    return keys


def _index_jai_by_title(jai_rows: list[JamfAppInstaller]) -> dict[str, JamfAppInstaller]:
    """
    Build a normalized-key → JAI row lookup tolerant of decorated titles.

    JAI titles routinely carry a version/year/edition suffix or a vendor
    prefix the Installomator label name omits, so an exact-equality match
    misses ~60 titles whose app *is* in the catalog (e.g. ``"SAP Privileges"``
    vs the ``privileges`` label). Each row is therefore indexed under several
    keys (see :func:`_jai_index_keys`). Two passes guarantee exact-title
    matches always beat a decoration-stripped one: every exact key is claimed
    first, then the stripped variants fill only the keys still unclaimed.
    """
    index: dict[str, JamfAppInstaller] = {}
    for j in jai_rows:
        key = _normalize_name(j.title)
        if key:
            index.setdefault(key, j)
    for j in jai_rows:
        for key in _jai_index_keys(j.title):
            index.setdefault(key, j)
    return index


def _match_jai(
    bundle_id: str | None,
    normalized_name: str,
    jai_by_bundle_id: dict[str, JamfAppInstaller],
    jai_by_title: dict[str, JamfAppInstaller],
) -> JamfAppInstaller | None:
    """
    Match a JAI title to an app: bundle_id first (exact, high confidence),
    falling back to normalized-name. bundle_id only covers the minority of
    apps that have one (~16% of labels, no casks), so name matching remains
    the workhorse; bundle_id is a precision overlay that also corrects the
    occasional name-match false positive.
    """
    if bundle_id and (hit := jai_by_bundle_id.get(bundle_id)):
        return hit
    return jai_by_title.get(normalized_name)


def _backfilled_bundle_id(own: str | None, matching_jai: JamfAppInstaller | None) -> str | None:
    """An app's own bundle_id, or JAI's when the app lacks one — JAI as a bundle_id provider."""
    if own:
        return own
    return matching_jai.bundle_id if matching_jai else None


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
    expected_team_id: str | None,
    sha256: str | None,
    sources: list[str],
    installomator_payload: dict | None,
    homebrew_payload: dict | None,
    autopkg_payload: dict | None,
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
    :param expected_team_id: Apple Team ID from the Installomator label, or None.
    :type expected_team_id: str | None
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
    :param jamf_app_installer_payload: JamfAppInstallerSource shape, or None.
    :type jamf_app_installer_payload: dict | None
    """
    apps_stmt = sqlite_insert(AppRow).values(
        slug=slug,
        bundle_id=bundle_id,
        name=name,
        vendor=vendor,
        current_version=current_version,
        download_url=download_url,
        install_method=install_method,
        expected_team_id=expected_team_id,
        sha256=sha256,
        sources=sources,
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
            "expected_team_id": apps_stmt.excluded.expected_team_id,
            "sha256": apps_stmt.excluded.sha256,
            "sources": apps_stmt.excluded.sources,
        },
    )
    await session.execute(apps_stmt)

    # Separate SELECT for the id: RETURNING + ON CONFLICT is broken in SQLite < 3.45 (Python 3.11/3.12 ship older).
    app_id = await session.scalar(select(AppRow.id).where(AppRow.slug == slug))

    detail_stmt = sqlite_insert(AppSourceDetailRow).values(
        app_id=app_id,
        installomator=installomator_payload,
        homebrew_cask=homebrew_payload,
        autopkg=autopkg_payload,
        jamf_app_installer=jamf_app_installer_payload,
    )
    detail_stmt = detail_stmt.on_conflict_do_update(
        index_elements=["app_id"],
        set_={
            "installomator": detail_stmt.excluded.installomator,
            "homebrew_cask": detail_stmt.excluded.homebrew_cask,
            "autopkg": detail_stmt.excluded.autopkg,
            "jamf_app_installer": detail_stmt.excluded.jamf_app_installer,
        },
    )
    await session.execute(detail_stmt)


def _match_aux(
    normalized: str,
    own_bundle: str | None,
    indexes: _StitchIndexes,
) -> tuple[list[AutopkgRecipe], JamfAppInstaller | None]:
    """
    Match the auxiliary (non-primary) sources both phases share: AutoPkg recipes
    by normalized name, and a JAI row by bundle_id-then-name. Neither ever creates
    an app; they only attach to the primary Installomator label or Cask.
    """
    matching_autopkg = indexes.autopkg_by_name.get(normalized, [])
    matching_jai = _match_jai(
        own_bundle, normalized, indexes.jai_by_bundle_id, indexes.jai_by_title
    )
    return matching_autopkg, matching_jai


def _resolve_label(il: InstallomatorLabel, indexes: _StitchIndexes) -> _ResolvedApp:
    """Resolve an Installomator label (plus any Cask/AutoPkg/JAI matches) into an upsertable app."""
    matching_cask = _find_matching_cask(il, indexes.casks_by_token, indexes.casks_by_app_name)
    display_name = il.display_name or il.name
    normalized = _normalize_name(display_name)
    own_bundle = il.package_id or CURATED_BUNDLE_IDS.get(il.name)
    matching_autopkg, matching_jai = _match_aux(normalized, own_bundle, indexes)

    sources = ["installomator"]
    if matching_cask is not None:
        sources.append("homebrew_cask")
    if matching_autopkg:
        sources.append("autopkg")
    if matching_jai is not None:
        sources.append("jamf_app_installer")

    return _ResolvedApp(
        upsert_kwargs={
            "slug": il.name,
            "bundle_id": _backfilled_bundle_id(own_bundle, matching_jai),
            "name": display_name,
            "vendor": _extract_vendor(il),
            "current_version": _resolve_version(il, matching_cask, matching_jai),
            "download_url": _resolve_download_url(il, matching_cask, matching_jai),
            "install_method": _resolve_install_method(il.install_type),
            "expected_team_id": il.expected_team_id,
            "sha256": matching_cask.sha256 if matching_cask else None,
            "sources": sources,
            "installomator_payload": _build_installomator_payload(il),
            "homebrew_payload": _build_cask_payload(matching_cask) if matching_cask else None,
            "autopkg_payload": (
                _build_autopkg_payload(matching_autopkg) if matching_autopkg else None
            ),
            "jamf_app_installer_payload": (
                _build_jai_payload(matching_jai) if matching_jai else None
            ),
        },
        matched_cask_token=matching_cask.token if matching_cask else None,
        has_autopkg=bool(matching_autopkg),
        has_jai=matching_jai is not None,
    )


def _resolve_cask(cask: HomebrewCask, indexes: _StitchIndexes) -> _ResolvedApp:
    """Resolve a Cask-only record (plus any AutoPkg/JAI matches) into an upsertable app."""
    cask_name = cask.name or cask.token
    normalized = _normalize_name(cask_name)
    # Casks carry no native bundle_id; a curated override or JAI hit can supply one.
    own_bundle = CURATED_BUNDLE_IDS.get(cask.token)
    matching_autopkg, matching_jai = _match_aux(normalized, own_bundle, indexes)

    sources = ["homebrew_cask"]
    if matching_autopkg:
        sources.append("autopkg")
    if matching_jai is not None:
        sources.append("jamf_app_installer")

    return _ResolvedApp(
        upsert_kwargs={
            "slug": cask.token,
            "bundle_id": _backfilled_bundle_id(own_bundle, matching_jai),
            "name": cask_name,
            "vendor": cask_name.split()[0] if cask_name else None,
            "current_version": cask.version or (matching_jai.version if matching_jai else None),
            "download_url": _clean_cask_url(cask) or _jai_external_url(matching_jai),
            "install_method": _infer_install_method_from_cask(cask),
            "expected_team_id": None,
            "sha256": cask.sha256,
            "sources": sources,
            "installomator_payload": None,
            "homebrew_payload": _build_cask_payload(cask),
            "autopkg_payload": (
                _build_autopkg_payload(matching_autopkg) if matching_autopkg else None
            ),
            "jamf_app_installer_payload": (
                _build_jai_payload(matching_jai) if matching_jai else None
            ),
        },
        matched_cask_token=None,
        has_autopkg=bool(matching_autopkg),
        has_jai=matching_jai is not None,
    )


async def _commit_app(session: AsyncSession, resolved: _ResolvedApp) -> bool:
    """
    Upsert one resolved app inside a SAVEPOINT so a single bad record can't poison
    the batch. Returns True on success; logs and returns False on any failure.
    """
    slug = resolved.upsert_kwargs["slug"]
    try:
        async with session.begin_nested():
            await _upsert_app_with_sources(session, **resolved.upsert_kwargs)
        return True
    except Exception as exc:
        log.warning("Failed to stitch %r: %s", slug, exc)
        return False


async def stitch_catalog(session: AsyncSession) -> tuple[int, int, int, int, int, int]:
    """
    Run the stitch process. Builds unified ``apps`` rows from ingested
    Installomator labels, Homebrew Cask records, AutoPkg recipe-index entries,
    and Jamf App Installers catalog rows.

    Phases:

    1. **Installomator-led.** For each label, try to match a Cask (token or
       artifact app-name), any AutoPkg recipes (by normalized display name),
       and any JAI catalog row (by normalized display name). Upsert one
       ``apps`` row per label. Sources land in canonical ordering
       ``[installomator, homebrew_cask, autopkg, jamf_app_installer]``
       regardless of which combination is present.
    2. **Cask-only.** Walk Casks not claimed in phase 1, with AutoPkg + JAI
       name matching still attempted.

    **AutoPkg and JAI never create new apps.** Both are coverage indicators
    attached to existing apps when their normalized name matches the app's
    display name.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :return: ``(installomator_apps, cask_only_apps, both_sources,
        autopkg_attached_apps, jai_attached_apps, failed)``.

        - ``installomator_apps`` is the count of apps with an Installomator source
        - ``cask_only_apps`` is the count of apps with only a Cask source
        - ``both_sources`` is the subset of ``installomator_apps`` that also matched a Cask
        - ``autopkg_attached_apps`` is the count of apps with one or more
          AutoPkg recipes attached (across all phases)
        - ``jai_attached_apps`` is the count of apps with a JAI catalog row
          attached (across all phases)
        - ``failed`` is the count of records that raised an unexpected error
    :rtype: tuple[int, int, int, int, int, int]
    """
    labels = (await session.scalars(select(InstallomatorLabel))).all()
    casks = (await session.scalars(select(HomebrewCask))).all()
    autopkg_recipes = (await session.scalars(select(AutopkgRecipe))).all()
    jai_rows = (await session.scalars(select(JamfAppInstaller))).all()

    indexes = _StitchIndexes.build(list(casks), list(autopkg_recipes), list(jai_rows))
    matched_cask_tokens: set[str] = set()

    installomator_count = both_sources = cask_only_count = 0
    autopkg_attached_count = jai_attached_count = failed = 0

    # Phase 1: Installomator-led. Each label upserts one app, claiming a Cask if matched.
    for il in labels:
        resolved = _resolve_label(il, indexes)
        if not await _commit_app(session, resolved):
            failed += 1
            continue
        installomator_count += 1
        if resolved.matched_cask_token is not None:
            matched_cask_tokens.add(resolved.matched_cask_token)
            both_sources += 1
        autopkg_attached_count += resolved.has_autopkg
        jai_attached_count += resolved.has_jai

    # Phase 2: Cask-only. Walk Casks no label claimed.
    for cask in casks:
        if cask.token in matched_cask_tokens:
            continue
        resolved = _resolve_cask(cask, indexes)
        if not await _commit_app(session, resolved):
            failed += 1
            continue
        cask_only_count += 1
        autopkg_attached_count += resolved.has_autopkg
        jai_attached_count += resolved.has_jai

    await session.commit()

    # Expire the identity map: the Core upserts above bypass the ORM, so objects loaded earlier would read stale.
    session.expire_all()

    return (
        installomator_count,
        cask_only_count,
        both_sources,
        autopkg_attached_count,
        jai_attached_count,
        failed,
    )
