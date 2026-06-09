"""
Cross-source version drift detection.

Pure projection — no I/O. The route handler reads the apps row + source
detail from the DB and hands them to :func:`detect_drift`. Drift is
defined as two or more versioned sources disagreeing on what the
current latest version is. ``packaging.version.Version`` does the
semantic compare so ``4.32`` and ``4.32.0`` are treated as equal, and
when a version string can't be parsed the comparison falls back to a
case-insensitive string equality (different unparseable strings still
count as drift).
"""

from typing import Any

from packaging.version import InvalidVersion, Version

from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.drift import DriftEntry, DriftResponse, SourceVersion

VERSIONED_SOURCES: tuple[str, ...] = ("installomator", "homebrew_cask")


def extract_versions(detail: AppSourceDetailRow | None) -> dict[str, str]:
    """
    Pull the per-source version string out of an app's source detail.

    Returns a dict keyed by source name (``installomator``,
    ``homebrew_cask``). Sources with no extractable version (missing
    payload, missing version field, shell-expression value) are omitted
    so callers can rely on ``len(...)`` for "how many versioned sources
    does this app have."

    :param detail: The ``app_source_details`` row, or ``None``.
    :return: Mapping of source name to version string.
    """
    if detail is None:
        return {}

    out: dict[str, str] = {}

    inst = _extract_installomator_version(detail.installomator)
    if inst is not None:
        out["installomator"] = inst

    cask = _extract_homebrew_cask_version(detail.homebrew_cask)
    if cask is not None:
        out["homebrew_cask"] = cask

    return out


def detect_drift(app_row: AppRow, detail: AppSourceDetailRow | None) -> DriftEntry | None:
    """
    Compute drift for a single app.

    Returns ``None`` when fewer than two sources expose a version or when
    all versions are equivalent (PEP-440 equal for parseable values,
    case-insensitive string equality otherwise). Returns a
    :class:`DriftEntry` when sources disagree.

    :param app_row: The ``apps`` table row.
    :param detail: The matching ``app_source_details`` row, or ``None``.
    :return: A drift entry, or ``None`` if no drift.
    """
    versions = extract_versions(detail)
    if len(versions) < 2:
        return None

    parsed: dict[str, Version | None] = {}
    for source, raw in versions.items():
        try:
            parsed[source] = Version(raw)
        except InvalidVersion:
            parsed[source] = None

    if _all_equivalent(versions, parsed):
        return None

    leader: str | None = None
    laggard: str | None = None
    if all(p is not None for p in parsed.values()):
        leader = max(parsed, key=lambda s: parsed[s])  # type: ignore[arg-type]
        laggard = min(parsed, key=lambda s: parsed[s])  # type: ignore[arg-type]

    return DriftEntry(
        slug=app_row.slug,
        name=app_row.name,
        vendor=app_row.vendor,
        versions=[
            SourceVersion(source=source, version=raw, parsed_ok=parsed[source] is not None)
            for source, raw in versions.items()
        ],
        leader=leader,
        laggard=laggard,
    )


def _extract_installomator_version(payload: dict[str, Any] | None) -> str | None:
    """
    Pull ``appNewVersion`` out of an Installomator source payload.

    Skips unresolved shell expressions — command substitution
    (``$(...)``), parameter expansion (``${...}``), pipelines, and
    legacy backtick substitution. These reference variables or external
    commands that aren't evaluated at ingest time, so the literal stored
    value isn't a real version and would only generate drift noise.
    Returns ``None`` if the field is missing, empty, or such an
    expression.
    """
    if not payload:
        return None
    raw = payload.get("raw") or {}
    value = raw.get("appNewVersion")
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if _is_shell_expression(value):
        return None
    return value


def _is_shell_expression(value: str) -> bool:
    """
    True if ``value`` looks like an unresolved bash expression.

    Real version strings are alphanumeric with ``.``, ``-``, ``_``, and
    occasional commas (e.g. ``2.14,2026.03``). They never contain ``$``
    (parameter expansion / command substitution), ``|`` (pipelines), or
    backticks (legacy substitution), so any of those characters anywhere
    in the string is a reliable "this isn't a version" signal.
    """
    return any(ch in value for ch in ("$", "|", "`"))


def _extract_homebrew_cask_version(payload: dict[str, Any] | None) -> str | None:
    """
    Pull ``version`` out of a Homebrew Cask source payload.

    Skips Cask's ``:latest`` sentinel (means "no versioning declared") so
    it doesn't pollute drift comparisons.
    """
    if not payload:
        return None
    cask = payload.get("cask_json") or {}
    value = cask.get("version")
    if not isinstance(value, str) or not value.strip():
        return None
    if value.strip().lower() == "latest":
        return None
    return value.strip()


def _all_equivalent(
    raw: dict[str, str],
    parsed: dict[str, Version | None],
) -> bool:
    """
    True iff every version in ``raw`` is equivalent under our compare rules.

    Parseable versions compare via ``packaging.Version`` equality (so
    ``4.32`` == ``4.32.0``); unparseable versions compare via stripped
    case-insensitive string equality. Mixing parseable + unparseable is
    treated as not-equivalent (i.e. drift) because we can't establish
    semantic equality without a common version space.
    """
    sources = list(raw.keys())
    first = sources[0]
    first_parsed = parsed[first]

    for source in sources[1:]:
        other_parsed = parsed[source]
        if first_parsed is not None and other_parsed is not None:
            if first_parsed != other_parsed:
                return False
        elif first_parsed is None and other_parsed is None:
            if raw[first].strip().casefold() != raw[source].strip().casefold():
                return False
        else:
            return False
    return True


def scan_drift(rows: list[AppRow], *, source: str | None, limit: int, offset: int) -> DriftResponse:
    """
    Scan already-fetched app rows for cross-source version drift.

    Shared by the REST ``/apps/drift`` route and the MCP ``list_drift`` tool.
    """
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
    )
