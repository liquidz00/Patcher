"""
Pydantic models for Patcher's on-disk configuration.

:class:`PatcherSettings` is the single source of truth for everything stored in
the property list — UI branding, the matching toggle, integration flags,
ignored titles, and the recorded interpreter path. It owns reading and writing
the plist (:meth:`~PatcherSettings.load` / :meth:`~PatcherSettings.save`) and
migrating older on-disk formats forward.
"""

import plistlib
import shutil
import sys
from enum import Enum
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator

from . import Model

SETTINGS_PATH = Path.home() / "Library/Application Support/Patcher/com.liquidzoo.patcher.plist"

# Top-level keys that mark a pre-v2 (nested) plist still needing migration.
_LEGACY_V1_KEYS = ("Setup", "UI", "InstallomatorClient")


class UIConfigKeys(str, Enum):
    """Plist keys for the user-interface settings block."""

    HEADER = "header_text"
    FOOTER = "footer_text"
    FONT_NAME = "font_name"
    REG_FONT_PATH = "reg_font_path"
    BOLD_FONT_PATH = "bold_font_path"
    LOGO_PATH = "logo_path"
    HEADER_COLOR = "header_color"


class UIDefaults(Model):
    """Default branding values for PDF and HTML reports (header/footer text, fonts, logo, color)."""

    model_config = ConfigDict(validate_assignment=True)

    header_text: str = Field(default="Default header text", min_length=1)
    footer_text: str = Field(default="Default footer text", min_length=1)
    font_name: str = Field(default="Assistant", min_length=1)
    reg_font_path: str = ""
    bold_font_path: str = ""
    header_color: str = Field(default="#6432bdff", min_length=1)
    logo_path: str = ""


class Integrations(Model):
    """Per-source matching toggles. Only ``installomator`` and ``homebrew`` are wired today."""

    installomator: bool = True
    homebrew: bool = False
    autopkg: bool = False
    jai: bool = False


class PatcherSettings(Model):
    """
    Patcher's complete on-disk configuration, backed by the property list.

    The single home for everything persisted between runs: setup completion,
    the matching and caching toggles, the interpreter path recorded for the #68
    preflight, UI branding, integration flags, and the user's ignored-title
    patterns. :meth:`load` reads and migrates the plist; :meth:`save` writes the
    whole model back; the ``_migrate`` validator folds every older format
    forward in one place.

    .. versionadded:: 3.3.0
        Replaces the former ``PropertyListManager`` and ``UIConfigManager``,
        consolidating plist I/O and format migration into one model.
    """

    model_config = ConfigDict(populate_by_name=True)

    setup_completed: bool = False
    enable_matching: bool = True
    enable_caching: bool = True
    interpreter_path: str = Field(default_factory=lambda: sys.executable)
    user_interface_settings: UIDefaults = Field(
        default_factory=UIDefaults, alias="UserInterfaceSettings"
    )
    integrations: Integrations = Field(default_factory=Integrations)
    ignored_titles: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "PatcherSettings":
        """
        Read settings from ``path``, migrating older plist formats forward.

        A missing file yields a defaults-only instance. When a pre-v2 (nested)
        plist is detected, a ``.bak`` copy is written before migrating so the
        original is never lost.
        """
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = plistlib.load(f)
        legacy = any(key in data for key in _LEGACY_V1_KEYS)
        if legacy:
            shutil.copy(path, path.with_suffix(".bak"))
        settings = cls.model_validate(data)
        if legacy:  # persist the upgraded format
            settings.save(path)
        return settings

    def save(self, path: Path = SETTINGS_PATH) -> None:
        """Write the full settings model to ``path`` as a property list."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            plistlib.dump(self.model_dump(mode="python", by_alias=True, exclude_none=True), f)

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: dict) -> dict:
        """
        Fold any older on-disk shape forward to the current schema.

        One migration home for both the v1 nested format (``Setup`` / ``UI`` /
        ``InstallomatorClient`` sections) and the v2 flat format
        (``enable_installomator`` / ``enable_homebrew``).
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)

        if any(key in data for key in _LEGACY_V1_KEYS):  # v1 -> current
            ui = data.get("UI") or {}
            ui_settings = {
                UIConfigKeys.HEADER.value: ui.get("HEADER_TEXT"),
                UIConfigKeys.FOOTER.value: ui.get("FOOTER_TEXT"),
                UIConfigKeys.FONT_NAME.value: ui.get("FONT_NAME"),
                UIConfigKeys.REG_FONT_PATH.value: ui.get("FONT_REGULAR_PATH"),
                UIConfigKeys.BOLD_FONT_PATH.value: ui.get("FONT_BOLD_PATH"),
                UIConfigKeys.LOGO_PATH.value: ui.get("LOGO_PATH"),
            }
            return {
                "setup_completed": data.get("Setup", {}).get("first_run_done", False),
                "enable_matching": data.get("InstallomatorClient", {}).get("enabled", True),
                "enable_caching": True,
                "UserInterfaceSettings": {k: v for k, v in ui_settings.items() if v is not None},
            }

        if "enable_installomator" in data:  # v2 -> current
            data.setdefault("enable_matching", data.pop("enable_installomator"))
            data.setdefault("integrations", {})
            data["integrations"].setdefault("installomator", data["enable_matching"])
        if "enable_homebrew" in data:
            data.setdefault("integrations", {})
            data["integrations"].setdefault("homebrew", data.pop("enable_homebrew"))

        return data
