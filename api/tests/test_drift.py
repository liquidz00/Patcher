"""Unit tests for :mod:`patcher_api.drift`."""

from types import SimpleNamespace

import pytest
from patcher_api.drift import (
    VERSIONED_SOURCES,
    _all_equivalent,
    detect_drift,
    extract_versions,
)

from patcher.catalog import DriftEntry


def _detail(*, installomator=None, homebrew_cask=None):
    return SimpleNamespace(installomator=installomator, homebrew_cask=homebrew_cask)


def _inst(version):
    return {
        "label_name": "x",
        "label_url": "https://example.test/x",
        "raw": {"appNewVersion": version} if version is not None else {},
    }


def _cask(version):
    return {"token": "x", "cask_json": {"version": version} if version is not None else {}}


def _app(slug="testapp", name="Test App", vendor="Test Vendor"):
    return SimpleNamespace(slug=slug, name=name, vendor=vendor)


def test_versioned_sources_only_includes_installomator_and_cask():
    """MAS, AutoPkg, JAI deliberately excluded — see project_patcher_mas_low_value memory."""
    assert VERSIONED_SOURCES == ("installomator", "homebrew_cask")


def test_extract_versions_returns_empty_for_none_detail():
    assert extract_versions(None) == {}


def test_extract_versions_returns_empty_for_payload_without_versions():
    detail = _detail(installomator={"raw": {}}, homebrew_cask={"cask_json": {}})
    assert extract_versions(detail) == {}


def test_extract_versions_pulls_installomator_app_new_version():
    detail = _detail(installomator=_inst("4.32.0"))
    assert extract_versions(detail) == {"installomator": "4.32.0"}


def test_extract_versions_pulls_homebrew_cask_version():
    detail = _detail(homebrew_cask=_cask("4.40.0"))
    assert extract_versions(detail) == {"homebrew_cask": "4.40.0"}


def test_extract_versions_returns_both_when_both_present():
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("4.40.0"))
    assert extract_versions(detail) == {
        "installomator": "4.32.0",
        "homebrew_cask": "4.40.0",
    }


def test_extract_versions_skips_installomator_shell_expression():
    """``appNewVersion=$(curl ...)`` is unresolved at ingest, can't compare."""
    detail = _detail(installomator=_inst("$(curl -fs https://example.test | jq -r .version)"))
    assert extract_versions(detail) == {}


def test_extract_versions_skips_installomator_parameter_expansion():
    """``${appNewVersion:0:-3}`` references another variable; never literal."""
    detail = _detail(installomator=_inst("${appNewVersion:0:-3}"))
    assert extract_versions(detail) == {}


def test_extract_versions_skips_installomator_parameter_expansion_with_transform():
    """``${rawVersion// build /.}`` is a parameter expansion with replacement."""
    detail = _detail(installomator=_inst("${rawVersion// build /.}"))
    assert extract_versions(detail) == {}


def test_extract_versions_skips_installomator_pipeline():
    """A truncated ``$()`` exposing the raw pipeline still has ``|`` to catch it."""
    detail = _detail(
        installomator=_inst("curl -fsI ${downloadURL} | tr -d '\\r' | grep -i ^location")
    )
    assert extract_versions(detail) == {}


def test_extract_versions_skips_installomator_backtick_substitution():
    detail = _detail(installomator=_inst("`curl -fs https://example.test/version`"))
    assert extract_versions(detail) == {}


def test_extract_versions_keeps_unusual_but_real_versions():
    """Versions with commas, dates, suffixes are legitimate — must not be skipped."""
    cases = [
        "2.14,2026.03",  # silentknight-style resolved
        "0.2026.05.20.09.21.stable_03",  # warp-style resolved
        "5.2.2.32209",  # beyondcompare-style resolved
        "1.5.4",  # plain semver
    ]
    for version in cases:
        detail = _detail(installomator=_inst(version))
        assert extract_versions(detail) == {"installomator": version}, version


def test_extract_versions_skips_cask_latest_sentinel():
    """Cask's ``:latest`` means no versioning declared, not a real version."""
    detail = _detail(homebrew_cask=_cask("latest"))
    assert extract_versions(detail) == {}


def test_extract_versions_strips_whitespace():
    detail = _detail(installomator=_inst("  4.32.0  "), homebrew_cask=_cask("\t4.40.0\n"))
    assert extract_versions(detail) == {
        "installomator": "4.32.0",
        "homebrew_cask": "4.40.0",
    }


def test_extract_versions_skips_empty_strings():
    detail = _detail(installomator=_inst(""), homebrew_cask=_cask("   "))
    assert extract_versions(detail) == {}


def test_extract_versions_handles_missing_raw_key():
    detail = _detail(installomator={"label_name": "x"})
    assert extract_versions(detail) == {}


def test_extract_versions_handles_missing_cask_json_key():
    detail = _detail(homebrew_cask={"token": "x"})
    assert extract_versions(detail) == {}


def test_detect_drift_returns_none_when_no_versioned_sources():
    assert detect_drift(_app(), None) is None


def test_detect_drift_returns_none_when_only_one_versioned_source():
    """Drift needs ≥2 sources to compare."""
    detail = _detail(installomator=_inst("4.32.0"))
    assert detect_drift(_app(), detail) is None


def test_detect_drift_returns_none_when_versions_string_equal():
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("4.32.0"))
    assert detect_drift(_app(), detail) is None


def test_detect_drift_returns_none_when_versions_semver_equal():
    """4.32 == 4.32.0 under packaging.Version. Per Andrew's --strict decision."""
    detail = _detail(installomator=_inst("4.32"), homebrew_cask=_cask("4.32.0"))
    assert detect_drift(_app(), detail) is None


def test_detect_drift_returns_entry_when_versions_differ():
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("4.40.0"))
    entry = detect_drift(_app(slug="slack"), detail)

    assert isinstance(entry, DriftEntry)
    assert entry.slug == "slack"
    assert {v.source for v in entry.versions} == {"installomator", "homebrew_cask"}
    assert {v.version for v in entry.versions} == {"4.32.0", "4.40.0"}
    assert all(v.parsed_ok for v in entry.versions)


def test_detect_drift_assigns_leader_and_laggard_when_all_parseable():
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("4.40.0"))
    entry = detect_drift(_app(), detail)

    assert entry is not None
    assert entry.leader == "homebrew_cask"
    assert entry.laggard == "installomator"


def test_detect_drift_omits_leader_laggard_when_any_unparseable():
    """Date-style Cask versions (``2025-04-15``) can't compare to PEP-440."""
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("2025-04-15"))
    entry = detect_drift(_app(), detail)

    assert entry is not None
    assert entry.leader is None
    assert entry.laggard is None
    assert {v.parsed_ok for v in entry.versions} == {True, False}


def test_detect_drift_flags_mixed_parseable_unparseable_as_drift():
    """Can't establish semantic equality across version spaces — count as drift."""
    detail = _detail(installomator=_inst("4.32.0"), homebrew_cask=_cask("not-a-version"))
    entry = detect_drift(_app(), detail)

    assert entry is not None


def test_detect_drift_flags_two_unparseable_but_unequal_strings():
    detail = _detail(installomator=_inst("2025-04-15"), homebrew_cask=_cask("2025-05-01"))
    entry = detect_drift(_app(), detail)

    assert entry is not None


def test_detect_drift_treats_two_unparseable_equal_strings_as_agreement():
    detail = _detail(installomator=_inst("Beta 5"), homebrew_cask=_cask("beta 5"))
    assert detect_drift(_app(), detail) is None


def test_detect_drift_carries_app_metadata_through():
    detail = _detail(installomator=_inst("1.0"), homebrew_cask=_cask("2.0"))
    entry = detect_drift(_app(slug="zoom", name="Zoom", vendor="Zoom Video"), detail)

    assert entry is not None
    assert entry.slug == "zoom"
    assert entry.name == "Zoom"
    assert entry.vendor == "Zoom Video"


@pytest.mark.parametrize(
    "left,right,expected_equal",
    [
        ("1.0", "1.0", True),
        ("1.0", "1.0.0", True),
        ("1.0.0", "1.0.1", False),
        ("4.32", "4.32.0", True),
        ("4.32.0", "4.32.1", False),
    ],
)
def test_all_equivalent_parseable_pair(left, right, expected_equal):
    from packaging.version import Version

    raw = {"a": left, "b": right}
    parsed = {"a": Version(left), "b": Version(right)}
    assert _all_equivalent(raw, parsed) is expected_equal
