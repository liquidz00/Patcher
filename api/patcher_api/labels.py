"""
Installomator label generation — projects ingested catalog data into the
Installomator label format that consumers can drop into their Installomator
deployments.

The projection merges fields from both source payloads when available:

- ``name`` — prefers Homebrew Cask's display name; falls back to the apps row.
- ``type`` — prefers Installomator's explicit ``type``; falls back to the apps
  row's ``install_method``; last resort is URL extension.
- ``downloadURL`` — prefers Homebrew Cask's ``url`` (typically fresher than
  Installomator's static value); falls back to Installomator's ``downloadURL``
  if it's a literal (not a shell expression); last resort is the apps row.
- ``appNewVersion`` — uses the apps row's ``current_version`` (already merged
  during stitch — literal Installomator value preferred, Cask fallback).
- ``expectedTeamID`` — **only** available from Installomator. If the app is
  Cask-only, we emit a warning and omit the field; consumers must determine
  this manually (e.g., via ``codesign -dvvv`` on the downloaded artifact)
  before the label is deployable.

Pure projection — no I/O. The route handler reads the apps row + source
detail from the DB and hands them to :func:`build_installomator_label`.
"""

from typing import Any

from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from patcher_api.schemas.labels import GenerateLabelResponse


def build_installomator_label(
    app_row: AppRow,
    detail: AppSourceDetailRow | None,
) -> GenerateLabelResponse:
    """
    Project an apps row + source detail into an Installomator label.

    :param app_row: The ``apps`` table row for this slug.
    :type app_row: :class:`AppRow`
    :param detail: The matching ``app_source_details`` row, or ``None`` if
        the app has no source detail attached (rare — usually a leftover seed
        record).
    :type detail: :class:`AppSourceDetailRow` | None
    :return: Generated label content + provenance metadata.
    :rtype: :class:`GenerateLabelResponse`
    """
    warnings: list[str] = []

    cask_payload = detail.homebrew_cask if detail else None
    installomator_payload = detail.installomator if detail else None

    cask_json: dict[str, Any] = (
        cask_payload.get("cask_json", {}) if isinstance(cask_payload, dict) else {}
    )
    installo_raw: dict[str, Any] = (
        installomator_payload.get("raw", {}) if isinstance(installomator_payload, dict) else {}
    )

    name = _resolve_name(app_row, cask_json, installo_raw)
    install_type = _resolve_type(app_row, cask_json, installo_raw, warnings)
    download_url = _resolve_download_url(app_row, cask_json, installo_raw, warnings)
    version = app_row.current_version
    team_id = installo_raw.get("expectedTeamID")

    if not team_id:
        warnings.append(
            "expectedTeamID unknown — Installomator requires this for code-sign verification. "
            "Determine manually via `codesign -dvvv <path-to-app>` before deploying."
        )

    if not version:
        warnings.append(
            "appNewVersion is null — likely an Installomator label with a shell-expression "
            "value that pyinstallomator hasn't yet resolved. Label will install whatever "
            "version downloadURL currently serves."
        )

    content = _build_label_dict(
        name=name,
        install_type=install_type,
        download_url=download_url,
        version=version,
        team_id=team_id,
    )

    return GenerateLabelResponse(
        label_name=app_row.slug,
        content=content,
        sources_used=_sources_used(installomator_payload, cask_payload),
        warnings=warnings,
    )


def _resolve_name(
    app_row: AppRow,
    cask_json: dict[str, Any],
    installo_raw: dict[str, Any],
) -> str | None:
    """Prefer Cask's ``name[0]``; fall back to apps row, then Installomator."""
    cask_names = cask_json.get("name")
    if isinstance(cask_names, list) and cask_names:
        first = cask_names[0]
        if isinstance(first, str) and first:
            return first
    if app_row.name:
        return app_row.name
    installo_name = installo_raw.get("name")
    if isinstance(installo_name, str) and installo_name:
        return installo_name
    return None


def _resolve_type(
    app_row: AppRow,
    cask_json: dict[str, Any],
    installo_raw: dict[str, Any],
    warnings: list[str],
) -> str | None:
    """
    Prefer Installomator's explicit ``type``. Fall back to apps row's
    ``install_method``. Last resort: infer from URL extension.
    """
    explicit = installo_raw.get("type")
    if isinstance(explicit, str) and explicit:
        return explicit
    if app_row.install_method:
        return app_row.install_method
    inferred = _infer_type_from_url(cask_json.get("url") or app_row.download_url)
    if inferred:
        warnings.append(f"Inferred install type {inferred!r} from URL extension.")
        return inferred
    warnings.append("Could not determine install type. Defaulting to 'dmg' — adjust manually.")
    return "dmg"


def _infer_type_from_url(url: str | None) -> str | None:
    """Map a URL's extension to an Installomator ``type`` value. None if unrecognized."""
    if not url:
        return None
    lower = url.lower()
    if lower.endswith(".dmg"):
        return "dmg"
    if lower.endswith(".pkg"):
        return "pkg"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".tbz") or lower.endswith(".tar.bz2"):
        return "tbz"
    return None


def _resolve_download_url(
    app_row: AppRow,
    cask_json: dict[str, Any],
    installo_raw: dict[str, Any],
    warnings: list[str],
) -> str | None:
    """
    Prefer Cask's ``url`` (typically fresher). Fall back to Installomator's
    literal ``downloadURL`` (skip if it's a shell expression we haven't resolved).
    Last resort: the apps row.
    """
    cask_url = cask_json.get("url")
    if isinstance(cask_url, str) and cask_url:
        return cask_url

    installo_url = installo_raw.get("downloadURL")
    if isinstance(installo_url, str) and installo_url and not installo_url.startswith("$("):
        return installo_url

    if app_row.download_url:
        return app_row.download_url

    warnings.append("downloadURL is unknown — label is not deployable without one.")
    return None


def _sources_used(
    installomator_payload: dict | None,
    cask_payload: dict | None,
) -> list[str]:
    sources: list[str] = []
    if installomator_payload:
        sources.append("installomator")
    if cask_payload:
        sources.append("homebrew_cask")
    return sources


def _build_label_dict(
    *,
    name: str | None,
    install_type: str | None,
    download_url: str | None,
    version: str | None,
    team_id: str | None,
) -> dict[str, Any]:
    """
    Build the resolved-fields dict using Installomator's variable names.

    Fields that couldn't be resolved are omitted entirely — their absence is
    explained in the ``warnings`` list returned alongside. Consumers shouldn't
    have to filter ``null`` values out before rendering the label.

    :return: Installomator variable name → value, omitting any unresolved fields.
    :rtype: dict[str, Any]
    """
    label: dict[str, Any] = {}
    if name:
        label["name"] = name
    if install_type:
        label["type"] = install_type
    if download_url:
        label["downloadURL"] = download_url
    if version:
        label["appNewVersion"] = version
    if team_id:
        label["expectedTeamID"] = team_id
    return label
