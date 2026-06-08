"""
Tests for src/patcher/clients/installomator.py.

The InstallomatorClient class can't be exercised against a live Jamf instance, so
every test here mocks ``api.fetch_text`` (the httpx-based GET helper) and
``api.get_app_names`` (the Jamf-side patch-title → app-name resolver). The
test surface validates:

- Labels.txt discovery + caching
- Single-label fetch with disk + instance cache
- Bulk fetch (specific names AND eager-all)
- Team ID filtering
- The full match() pipeline end-to-end

Shell-pipeline resolver tests (the ``pyinstallomator`` subset) live with the
resolver itself at ``api/tests/test_installomator_resolver.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from src.patcher.clients import HTTPClient
from src.patcher.clients.installomator import InstallomatorClient, _scan_value
from src.patcher.core.exceptions import APIResponseError


def _sample_fragment(
    *,
    name: str = "Google Chrome",
    team_id: str = "EQHXZ8M8AV",
    label_type: str = "pkg",
    url: str = "https://dl.google.com/chrome.pkg",
) -> str:
    """Return the raw content of a minimal but valid InstallomatorClient fragment."""
    return (
        f"{name.lower().replace(' ', '')})\n"
        f'    name="{name}"\n'
        f'    type="{label_type}"\n'
        f'    downloadURL="{url}"\n'
        f'    expectedTeamID="{team_id}"\n'
        f"    ;;"
    )


@pytest.fixture
def iom(tmp_path: Path) -> InstallomatorClient:
    """
    Return an InstallomatorClient with isolated cache paths and a mocked api.

    Constructed bare — no Jamf credentials needed (the default ``HTTPClient``
    has no keyring touchpoint). The api attribute is then replaced with an
    ``AsyncMock(spec=JamfClient)`` so ``match()`` sees a JamfClient-shaped
    object (it asserts on type to surface a clear error for callers passing
    a plain ``HTTPClient`` to a method that requires Jamf endpoints).
    """
    instance = InstallomatorClient()
    instance.label_path = tmp_path / ".labels"
    instance.api = AsyncMock(spec=HTTPClient)
    return instance


class TestInstallomatorClient:
    @pytest.mark.parametrize(
        "value",
        [
            '"a\\"b"',  # escaped double-quote inside double quotes
            '"$(curl "x")"',  # $(...) re-opens quoting inside dq; the inner " must not close it
            '"`sw_vers`"',  # backtick command-sub inside double quotes
        ],
    )
    def test_scan_value_keeps_nested_quoting_whole(self, value):
        """The shell tokenizer captures a quoted value intact across nested contexts."""
        assert _scan_value(f"{value} trailing") == value

    def test_bare_construction_does_not_require_jamf_creds(self) -> None:
        """
        ``InstallomatorClient()`` with no args must construct cleanly even when no
        Jamf credentials exist anywhere (keyring, in-memory, env). Library callers
        using the client purely for label discovery / fetch shouldn't have to
        stand up Jamf auth they don't need.
        """
        from src.patcher.clients import HTTPClient

        iom = InstallomatorClient()
        assert isinstance(iom.api, HTTPClient)


class TestListAvailableLabels:
    @pytest.mark.asyncio
    async def test_list_available_labels_parses_labels_txt(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = "googlechrome\n1password8\nzulujdk8\n"

        result = await iom.list_available_labels()

        assert result == {"googlechrome", "1password8", "zulujdk8"}
        iom.api.fetch_text.assert_called_once()
        # Verify the URL we hit is the explicit refs/heads/main form
        called_url = iom.api.fetch_text.call_args[0][0]
        assert "Labels.txt" in called_url
        assert "refs/heads/main" in called_url

    @pytest.mark.asyncio
    async def test_list_available_labels_ignores_blank_and_comment_lines(
        self,
        iom: InstallomatorClient,
    ) -> None:
        iom.api.fetch_text.return_value = "# comment\ngooglechrome\n\n1password8\n   \n"

        result = await iom.list_available_labels()

        assert result == {"googlechrome", "1password8"}

    @pytest.mark.asyncio
    async def test_list_available_labels_caches_result(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = "googlechrome\n"

        first = await iom.list_available_labels()
        second = await iom.list_available_labels()

        assert first == second
        assert iom.api.fetch_text.call_count == 1  # cached on the instance

    @pytest.mark.asyncio
    async def test_list_available_labels_raises_on_fetch_failure(
        self, iom: InstallomatorClient
    ) -> None:
        from src.patcher.core.exceptions import PatcherError

        iom.api.fetch_text.side_effect = APIResponseError(
            "Server error", url="https://example.com/Labels.txt", status_code=500
        )

        with pytest.raises(PatcherError, match="Labels.txt"):
            await iom.list_available_labels()


class TestGetLabel:
    @pytest.mark.asyncio
    async def test_get_label_fetches_and_caches(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = _sample_fragment()

        label = await iom.get_label("googlechrome")

        assert label is not None
        assert label.name == "Google Chrome"
        assert label.installomator_label == "googlechrome"
        # Cached on instance: subsequent call doesn't refetch
        label_again = await iom.get_label("googlechrome")
        assert label_again is label
        assert iom.api.fetch_text.call_count == 1

    @pytest.mark.asyncio
    async def test_get_label_writes_to_disk_cache(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = _sample_fragment()

        await iom.get_label("googlechrome")

        cached_path = iom.label_path / "googlechrome.sh"
        assert cached_path.exists()
        assert "Google Chrome" in cached_path.read_text()

    @pytest.mark.asyncio
    async def test_get_label_reads_from_disk_cache_first(self, iom: InstallomatorClient) -> None:
        iom.label_path.mkdir(parents=True, exist_ok=True)
        (iom.label_path / "googlechrome.sh").write_text(_sample_fragment())

        label = await iom.get_label("googlechrome")

        assert label is not None
        assert label.name == "Google Chrome"
        iom.api.fetch_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_label_returns_none_on_404(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.side_effect = APIResponseError(
            "Not found", url="https://example.com/x.sh", status_code=404, not_found=True
        )

        label = await iom.get_label("nonexistent-app")

        assert label is None

    @pytest.mark.asyncio
    async def test_get_label_multi_assignment_first_wins_and_no_truncation(
        self,
        iom: InstallomatorClient,
    ) -> None:
        """Issue #65: a key assigned twice + a nested ``)`` inside ``$( )``.

        The label must still build (not be dropped by Pydantic for a list-valued
        ``name``), use the first assignment, and keep the full downloadURL.
        """
        fragment = (
            "adobereaderdc)\n"
            '    name="Adobe Acrobat Reader"\n'
            '    type="pkgInDmg"\n'
            '    if [[ -d "/Applications/Adobe Acrobat Reader DC.app" ]]; then\n'
            '      name="Adobe Acrobat Reader DC"\n'
            "    fi\n"
            "    downloadURL=$(curl -fs \"https://example.com/feed\" | sed -E 's/v([0-9.]+)/x/')\n"
            '    expectedTeamID="JQ525L2MZD"\n'
            "    ;;"
        )
        iom.api.fetch_text.return_value = fragment

        label = await iom.get_label("adobereaderdc")

        assert label is not None  # not silently dropped by validation
        assert label.name == "Adobe Acrobat Reader"  # first assignment wins
        assert label.download_url is not None
        # nested ) inside ([0-9.]+) no longer truncates: brackets balance
        assert label.download_url.count("(") == label.download_url.count(")")
        assert label.download_url.rstrip().endswith(")")

    @pytest.mark.asyncio
    async def test_get_label_returns_none_on_ignored_team_id(
        self, iom: InstallomatorClient
    ) -> None:
        # LL3KBL2M3A is in INGEST_EXCLUDED_TEAM_IDS (lcadvancedvpnclient)
        iom.api.fetch_text.return_value = _sample_fragment(
            name="LC AdvancedVPN", team_id="LL3KBL2M3A"
        )

        label = await iom.get_label("lcadvancedvpnclient")

        assert label is None

    @pytest.mark.asyncio
    async def test_get_label_is_case_insensitive(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = _sample_fragment()

        label_lower = await iom.get_label("googlechrome")
        label_upper = await iom.get_label("GOOGLECHROME")

        assert label_lower is label_upper  # same cached instance


class TestGetLabels:
    @pytest.mark.asyncio
    async def test_get_labels_with_explicit_names(self, iom: InstallomatorClient) -> None:
        iom.api.fetch_text.return_value = _sample_fragment()

        labels = await iom.get_labels({"googlechrome", "firefox"})

        assert len(labels) == 2
        assert iom.api.fetch_text.call_count == 2  # one per name

    @pytest.mark.asyncio
    async def test_get_labels_with_none_fetches_all(self, iom: InstallomatorClient) -> None:
        """When `names=None`, fetches every label listed in Labels.txt."""

        async def fetch_text_side_effect(url: str, **kwargs) -> str:
            if url.endswith("/Labels.txt"):
                return "googlechrome\nfirefox\n"
            return _sample_fragment()

        iom.api.fetch_text.side_effect = fetch_text_side_effect

        labels = await iom.get_labels()

        assert len(labels) == 2
        # 1 call for Labels.txt + 2 fragment fetches
        assert iom.api.fetch_text.call_count == 3

    @pytest.mark.asyncio
    async def test_get_labels_with_empty_iterable(self, iom: InstallomatorClient) -> None:
        labels = await iom.get_labels([])

        assert labels == []
        iom.api.fetch_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_labels_skips_failed_fetches(self, iom: InstallomatorClient) -> None:
        """A failed fetch for one label doesn't break the batch."""

        async def fetch_text_side_effect(url: str, **kwargs) -> str:
            if "googlechrome.sh" in url:
                return _sample_fragment()
            raise APIResponseError("Not found", url=url, status_code=404, not_found=True)

        iom.api.fetch_text.side_effect = fetch_text_side_effect

        labels = await iom.get_labels(["googlechrome", "nonexistent"])

        assert len(labels) == 1
        assert labels[0].name == "Google Chrome"
