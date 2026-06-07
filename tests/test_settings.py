import plistlib
import sys

import pytest
from src.patcher.core.models.settings import PatcherSettings


def test_defaults():
    s = PatcherSettings()
    assert s.setup_completed is False
    assert s.enable_matching is True
    assert s.enable_caching is True
    assert s.interpreter_path == sys.executable
    assert s.integrations.installomator is True
    assert s.integrations.homebrew is False
    assert s.ignored_titles == []
    assert s.user_interface_settings.header_text == "Default header text"


def test_load_missing_returns_defaults(tmp_path):
    s = PatcherSettings.load(tmp_path / "does-not-exist.plist")
    assert s == PatcherSettings()


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "patcher.plist"
    original = PatcherSettings(
        setup_completed=True,
        enable_matching=False,
        ignored_titles=["Adobe *", "Jamf *"],
    )
    original.user_interface_settings.header_text = "AnyOrg Patch Report"
    original.save(path)

    assert PatcherSettings.load(path) == original


def test_save_uses_camelcase_alias(tmp_path):
    path = tmp_path / "patcher.plist"
    PatcherSettings().save(path)
    with path.open("rb") as f:
        raw = plistlib.load(f)
    assert "UserInterfaceSettings" in raw
    assert "user_interface_settings" not in raw


def test_migrate_v2_enable_installomator():
    s = PatcherSettings.model_validate({"enable_installomator": False, "interpreter_path": "/x"})
    assert s.enable_matching is False
    assert s.integrations.installomator is False


def test_migrate_v2_enable_homebrew():
    s = PatcherSettings.model_validate({"enable_homebrew": True, "interpreter_path": "/x"})
    assert s.integrations.homebrew is True


def test_migrate_v1_nested_format(tmp_path):
    path = tmp_path / "patcher.plist"
    v1 = {
        "Setup": {"first_run_done": True},
        "InstallomatorClient": {"enabled": False},
        "UI": {
            "HEADER_TEXT": "My Header",
            "FOOTER_TEXT": "My Footer",
            "FONT_NAME": "Assistant",
            "FONT_REGULAR_PATH": "/f/reg.ttf",
            "FONT_BOLD_PATH": "/f/bold.ttf",
            "LOGO_PATH": "/f/logo.png",
        },
    }
    with path.open("wb") as f:
        plistlib.dump(v1, f)

    s = PatcherSettings.load(path)

    assert s.setup_completed is True
    assert s.enable_matching is False
    assert s.user_interface_settings.header_text == "My Header"
    assert s.user_interface_settings.reg_font_path == "/f/reg.ttf"
    assert s.user_interface_settings.logo_path == "/f/logo.png"
    assert path.with_suffix(".bak").exists()  # original preserved


def test_migrate_v1_missing_ui_keys_fall_back_to_defaults(tmp_path):
    path = tmp_path / "patcher.plist"
    with path.open("wb") as f:
        plistlib.dump({"Setup": {"first_run_done": False}, "UI": {}}, f)

    s = PatcherSettings.load(path)
    assert s.user_interface_settings.header_text == "Default header text"
    assert s.enable_matching is True  # default when InstallomatorClient absent


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
