"""
Tests for :class:`patcher.core.patcher_client.PatcherClient` — specifically
the high-level convenience methods (``fetch_patches``, ``analyze``, ``export``)
that make the library API a first-class peer of the CLI.

The methods are thin delegations to existing primitives; tests verify the
delegation shape (right arguments threaded through, optional steps respected)
rather than re-testing the primitives themselves.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.models.settings import Integrations, PatcherSettings
from src.patcher.core.patcher_client import PatcherClient


@pytest.fixture
def patcher(mock_policy_response, mock_patch_title_response):
    """
    Real PatcherClient instance with mocked collaborators.

    Constructed via the in-memory credentials path so no keyring is touched.
    ``jamf``, ``data``, and ``api`` are then replaced with mocks so each
    convenience method test can stub specific return values without standing
    up real HTTP / disk infrastructure.
    """
    p = PatcherClient(
        client_id="test-cid",
        client_secret="test-csec",
        server="https://test.example.com",
    )
    p.jamf = AsyncMock()
    p.jamf.get_policies.return_value = mock_policy_response
    p.jamf.get_title_configs.return_value = mock_policy_response
    p.jamf.get_summaries.return_value = mock_patch_title_response
    p.data = AsyncMock()
    p.api = AsyncMock()
    p.api.list_apps.return_value = []
    p.api.get_jamf_index.return_value = {}
    return p


class TestFetchPatches:
    @pytest.mark.asyncio
    async def test_default_flow_runs_policies_summaries_and_match(
        self, patcher, mocker, mock_policy_response
    ):
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )

        result = await patcher.fetch_patches()

        patcher.jamf.get_title_configs.assert_awaited_once()
        patcher.jamf.get_summaries.assert_awaited_once_with(
            [config.get("id") for config in mock_policy_response]
        )
        mock_match.assert_awaited_once_with(
            patcher.jamf.get_summaries.return_value,
            jamf=patcher.jamf,
            api=patcher.api,
            include_homebrew=False,
        )
        assert result == patcher.jamf.get_summaries.return_value

    @pytest.mark.asyncio
    async def test_stamps_name_id_from_configs(self, patcher, mocker):
        """name_id is joined onto each title from its config's softwareTitleNameId."""
        mocker.patch("src.patcher.core.patcher_client.match_titles", new_callable=AsyncMock)

        titles = await patcher.fetch_patches()

        # Chrome's config (softwareTitleId "3") carries softwareTitleNameId "0BC".
        chrome = next(title for title in titles if title.title_id == "3")
        assert chrome.name_id == "0BC"

    @pytest.mark.asyncio
    async def test_match_homebrew_override_widens_match(self, patcher, mocker):
        """match_homebrew=True overrides the (default False) enable_homebrew toggle."""
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )

        await patcher.fetch_patches(match_homebrew=True)

        assert mock_match.await_args.kwargs["include_homebrew"] is True

    @pytest.mark.asyncio
    async def test_match_homebrew_defaults_to_enable_homebrew(self, patcher, mocker):
        """When match_homebrew is None, the construction-time enable_homebrew default applies."""
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )
        patcher.enable_homebrew = True

        await patcher.fetch_patches()

        assert mock_match.await_args.kwargs["include_homebrew"] is True

    @pytest.mark.asyncio
    async def test_skips_match_when_disabled(self, patcher, mocker):
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )

        await patcher.fetch_patches(match_installomator=False)

        mock_match.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_match_when_no_api_client(self, patcher, mocker):
        """When PatcherClient was constructed with enable_installomator=False, .api is None."""
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )
        patcher.api = None

        result = await patcher.fetch_patches()  # must not crash

        mock_match.assert_not_called()
        assert result == patcher.jamf.get_summaries.return_value

    @pytest.mark.asyncio
    async def test_include_ios_calls_append_ios_status(self, patcher, mocker):
        mock_append = mocker.patch(
            "src.patcher.core.patcher_client.append_ios_status",
            new_callable=AsyncMock,
        )
        mock_append.return_value = ["enriched"]

        result = await patcher.fetch_patches(include_ios=True)

        mock_append.assert_awaited_once_with(patcher.jamf.get_summaries.return_value, patcher.jamf)
        assert result == ["enriched"]

    @pytest.mark.asyncio
    async def test_omit_recent_hours_calls_omit_recent(self, patcher, mocker):
        mock_omit = mocker.patch(
            "src.patcher.core.patcher_client.omit_recent",
            new_callable=AsyncMock,
        )
        mock_omit.return_value = ["filtered"]

        result = await patcher.fetch_patches(omit_recent_hours=24)

        mock_omit.assert_awaited_once_with(patcher.jamf.get_summaries.return_value, hours=24)
        assert result == ["filtered"]

    @pytest.mark.asyncio
    async def test_sort_by_calls_sort_titles(self, patcher, mocker):
        mock_sort = mocker.patch(
            "src.patcher.core.patcher_client.sort_titles",
            new_callable=AsyncMock,
        )
        mock_sort.return_value = ["sorted"]

        result = await patcher.fetch_patches(sort_by="released")

        mock_sort.assert_awaited_once_with(patcher.jamf.get_summaries.return_value, "released")
        assert result == ["sorted"]


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_string_criteria_dispatches_via_title_filter_apply(self, patcher, mocker):
        """analyze() routes through TitleFilter.apply with the kebab-case criterion."""
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TitleFilter.apply")
        mock_apply.return_value = ["result"]

        result = await patcher.analyze(["titles"], criteria="most-installed")

        mock_apply.assert_called_once_with(["titles"], "most-installed", threshold=70.0, top_n=None)
        assert result == ["result"]

    @pytest.mark.asyncio
    async def test_threshold_and_top_n_threaded_through(self, patcher, mocker):
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TitleFilter.apply")
        mock_apply.return_value = []

        await patcher.analyze(["titles"], criteria="below-threshold", threshold=85.0, top_n=5)

        mock_apply.assert_called_once_with(["titles"], "below-threshold", threshold=85.0, top_n=5)

    @pytest.mark.asyncio
    async def test_invalid_string_criteria_raises_patcher_error(self, patcher):
        with pytest.raises(PatcherError, match="Invalid criteria"):
            await patcher.analyze([], criteria="not-a-real-criterion")


class TestAnalyzeExcel:
    @pytest.mark.asyncio
    async def test_dispatches_via_title_filter_apply_on_data_titles(self, patcher, mocker):
        """Pre-v3.0.1: --excel-file is accepted but unread; we filter data.titles."""
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TitleFilter.apply")
        mock_apply.return_value = ["filtered"]
        patcher.data = MagicMock()
        patcher.data.titles = ["cached-titles"]

        result = await patcher.analyze_excel("/tmp/report.xlsx", criteria="most-installed")

        mock_apply.assert_called_once_with(
            ["cached-titles"], "most-installed", threshold=70.0, top_n=None
        )
        assert result == ["filtered"]


class TestAnalyzeTrend:
    @pytest.mark.asyncio
    async def test_returns_trend_dataframe(self, patcher, mocker):
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TrendAnalysis.apply")
        fake_df = mocker.MagicMock()
        fake_df.empty = False
        mock_apply.return_value = fake_df

        patcher.data = MagicMock()
        patcher.data.get_cached_files.return_value = ["snap1", "snap2"]

        result = await patcher.analyze_trend("patch-adoption")

        mock_apply.assert_called_once_with(["snap1", "snap2"], "patch-adoption")
        assert result is fake_df

    @pytest.mark.asyncio
    async def test_save_to_writes_html(self, patcher, mocker, tmp_path):
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TrendAnalysis.apply")
        fake_df = mocker.MagicMock()
        fake_df.empty = False
        mock_apply.return_value = fake_df

        patcher.data = MagicMock()
        patcher.data.get_cached_files.return_value = ["snap1", "snap2"]

        out = tmp_path / "trend.html"
        await patcher.analyze_trend("patch-adoption", save_to=out)

        fake_df.to_html.assert_called_once_with(out, index=False)

    @pytest.mark.asyncio
    async def test_save_to_skipped_on_empty_dataframe(self, patcher, mocker, tmp_path):
        mock_apply = mocker.patch("src.patcher.core.patcher_client.TrendAnalysis.apply")
        fake_df = mocker.MagicMock()
        fake_df.empty = True
        mock_apply.return_value = fake_df

        patcher.data = MagicMock()
        patcher.data.get_cached_files.return_value = ["snap1", "snap2"]

        await patcher.analyze_trend("patch-adoption", save_to=tmp_path / "trend.html")

        fake_df.to_html.assert_not_called()


class TestDiff:
    @pytest.mark.asyncio
    async def test_default_routes_through_live_vs_cache(self, patcher, mocker):
        """No flags: fetch_patches + Diff.live_vs_cache."""

        fake_titles = ["t1", "t2"]
        mocker.patch.object(patcher, "fetch_patches", AsyncMock(return_value=fake_titles))
        fake_diff = mocker.MagicMock()
        fake_diff.compute.return_value = "result"
        mock_live = mocker.patch(
            "src.patcher.core.patcher_client.Diff.live_vs_cache",
            return_value=fake_diff,
        )
        mock_from_cache = mocker.patch(
            "src.patcher.core.patcher_client.Diff.from_cache",
        )

        result = await patcher.diff()

        mock_live.assert_called_once_with(fake_titles, patcher.data, since=None, all_time=False)
        mock_from_cache.assert_not_called()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_no_fetch_routes_through_from_cache(self, patcher, mocker):
        fake_fetch = mocker.patch.object(patcher, "fetch_patches", AsyncMock())
        fake_diff = mocker.MagicMock()
        fake_diff.compute.return_value = "result"
        mock_from_cache = mocker.patch(
            "src.patcher.core.patcher_client.Diff.from_cache",
            return_value=fake_diff,
        )

        await patcher.diff(no_fetch=True)

        fake_fetch.assert_not_called()
        mock_from_cache.assert_called_once_with(patcher.data, since=None, all_time=False)

    @pytest.mark.asyncio
    async def test_between_routes_through_from_cache_with_pair(self, patcher, mocker):
        from datetime import date

        fake_fetch = mocker.patch.object(patcher, "fetch_patches", AsyncMock())
        fake_diff = mocker.MagicMock()
        fake_diff.compute.return_value = "result"
        mock_from_cache = mocker.patch(
            "src.patcher.core.patcher_client.Diff.from_cache",
            return_value=fake_diff,
        )

        dates = (date(2026, 5, 17), date(2026, 5, 21))
        await patcher.diff(between=dates)

        fake_fetch.assert_not_called()
        mock_from_cache.assert_called_once_with(patcher.data, between=dates)

    @pytest.mark.asyncio
    async def test_since_threaded_through_to_live_vs_cache(self, patcher, mocker):
        from datetime import timedelta

        mocker.patch.object(patcher, "fetch_patches", AsyncMock(return_value=["t"]))
        fake_diff = mocker.MagicMock()
        fake_diff.compute.return_value = "result"
        mock_live = mocker.patch(
            "src.patcher.core.patcher_client.Diff.live_vs_cache",
            return_value=fake_diff,
        )

        await patcher.diff(since=timedelta(days=30))

        mock_live.assert_called_once_with(
            ["t"], patcher.data, since=timedelta(days=30), all_time=False
        )

    @pytest.mark.asyncio
    async def test_all_time_threaded_through_to_live_vs_cache(self, patcher, mocker):
        mocker.patch.object(patcher, "fetch_patches", AsyncMock(return_value=["t"]))
        fake_diff = mocker.MagicMock()
        fake_diff.compute.return_value = "result"
        mock_live = mocker.patch(
            "src.patcher.core.patcher_client.Diff.live_vs_cache",
            return_value=fake_diff,
        )

        await patcher.diff(all_time=True)

        mock_live.assert_called_once_with(["t"], patcher.data, since=None, all_time=True)

    @pytest.mark.asyncio
    async def test_since_and_all_time_mutually_exclusive(self, patcher):
        from datetime import timedelta

        with pytest.raises(PatcherError, match="mutually exclusive"):
            await patcher.diff(since=timedelta(days=30), all_time=True)

    @pytest.mark.asyncio
    async def test_between_cannot_combine_with_since(self, patcher):
        from datetime import date, timedelta

        with pytest.raises(PatcherError, match="cannot be combined"):
            await patcher.diff(
                between=(date(2026, 5, 17), date(2026, 5, 21)),
                since=timedelta(days=30),
            )

    @pytest.mark.asyncio
    async def test_between_redundant_with_no_fetch(self, patcher):
        from datetime import date

        with pytest.raises(PatcherError, match="redundant"):
            await patcher.diff(
                between=(date(2026, 5, 17), date(2026, 5, 21)),
                no_fetch=True,
            )


class TestDetectDrift:
    @pytest.mark.asyncio
    async def test_list_mode_routes_through_list_drift(self, patcher):
        fake_response = MagicMock()
        patcher.api.list_drift = AsyncMock(return_value=fake_response)
        patcher.api.get_app_drift = AsyncMock()

        result = await patcher.detect_drift(vendor="Mozilla", source="installomator", limit=50)

        patcher.api.list_drift.assert_awaited_once_with(
            vendor="Mozilla", source="installomator", limit=50, offset=0
        )
        patcher.api.get_app_drift.assert_not_called()
        assert result is fake_response

    @pytest.mark.asyncio
    async def test_slug_mode_routes_through_get_app_drift(self, patcher):
        fake_entry = MagicMock()
        patcher.api.get_app_drift = AsyncMock(return_value=fake_entry)
        patcher.api.list_drift = AsyncMock()

        result = await patcher.detect_drift(slug="firefox")

        patcher.api.get_app_drift.assert_awaited_once_with("firefox")
        patcher.api.list_drift.assert_not_called()
        assert result is fake_entry

    @pytest.mark.asyncio
    async def test_slug_with_vendor_raises(self, patcher):
        with pytest.raises(PatcherError, match="cannot be combined"):
            await patcher.detect_drift(slug="firefox", vendor="Mozilla")

    @pytest.mark.asyncio
    async def test_slug_with_source_raises(self, patcher):
        with pytest.raises(PatcherError, match="cannot be combined"):
            await patcher.detect_drift(slug="firefox", source="installomator")

    @pytest.mark.asyncio
    async def test_offset_threaded_through(self, patcher):
        patcher.api.list_drift = AsyncMock(return_value=MagicMock())

        await patcher.detect_drift(offset=20)

        patcher.api.list_drift.assert_awaited_once_with(
            vendor=None, source=None, limit=100, offset=20
        )

    @pytest.mark.asyncio
    async def test_constructs_own_api_when_installomator_disabled(self, mocker):
        """When ``enable_installomator=False`` the standing self.api is None."""
        local = PatcherClient(
            client_id="x",
            client_secret="x",
            server="https://x.example.com",
            enable_installomator=False,
        )
        assert local.api is None

        fake_response = MagicMock()
        fake_api = AsyncMock()
        fake_api.list_drift = AsyncMock(return_value=fake_response)
        api_class = mocker.patch(
            "src.patcher.core.patcher_client.PatcherAPIClient",
            return_value=fake_api,
        )

        result = await local.detect_drift()

        api_class.assert_called_once_with()
        fake_api.list_drift.assert_awaited_once()
        fake_api.aclose.assert_awaited_once()
        assert result is fake_response


class TestReset:
    @pytest.mark.asyncio
    async def test_cache_calls_data_reset(self, patcher):
        patcher.data.reset_cache = MagicMock(return_value=True)
        await patcher.reset("cache")
        patcher.data.reset_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_failure_raises(self, patcher):
        patcher.data.reset_cache = MagicMock(return_value=False)
        with pytest.raises(PatcherError, match="Reset cache"):
            await patcher.reset("cache")

    @pytest.mark.asyncio
    async def test_in_memory_mode_blocks_non_cache_reset(self, patcher):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = True

        with pytest.raises(PatcherError, match="in-memory"):
            await patcher.reset("creds")
        with pytest.raises(PatcherError, match="in-memory"):
            await patcher.reset("UI")
        with pytest.raises(PatcherError, match="in-memory"):
            await patcher.reset("full")

    @pytest.mark.asyncio
    async def test_creds_all_calls_reset_config(self, patcher):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False

        await patcher.reset("creds")

        patcher._config.reset_config.assert_called_once()
        patcher._config.set_credential.assert_not_called()

    @pytest.mark.asyncio
    async def test_creds_with_credential_arg_clears_one_key(self, patcher):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False

        await patcher.reset("creds", credential="url")

        patcher._config.set_credential.assert_called_once_with("URL", "")
        patcher._config.reset_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_ui_resets_user_interface_settings(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        mock_settings_cls = mocker.patch("src.patcher.core.patcher_client.PatcherSettings")
        mock_settings = mock_settings_cls.load.return_value

        await patcher.reset("UI")

        mock_settings_cls.load.assert_called_once()
        mock_settings.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_runs_every_reset(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        patcher.data.reset_cache = MagicMock(return_value=True)
        mock_settings_cls = mocker.patch("src.patcher.core.patcher_client.PatcherSettings")
        mock_settings = mock_settings_cls.load.return_value

        await patcher.reset("full")

        patcher._config.reset_config.assert_called_once()
        mock_settings.save.assert_called_once()
        assert mock_settings.setup_completed is False
        patcher.data.reset_cache.assert_called_once()


class TestFromState:
    def test_reads_ui_and_installomator_from_state(self, mocker):
        settings = PatcherSettings(enable_matching=True, integrations=Integrations(homebrew=True))
        settings.user_interface_settings.header_text = "Org Header"
        mocker.patch("src.patcher.core.patcher_client.PatcherSettings.load", return_value=settings)
        mock_config_cls = mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state()

        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["config"] is mock_config_cls.return_value
        assert call_kwargs["enable_installomator"] is True
        assert call_kwargs["enable_homebrew"] is True
        assert call_kwargs["ui_config"]["header_text"] == "Org Header"

    def test_overrides_take_precedence(self, mocker):
        mocker.patch(
            "src.patcher.core.patcher_client.PatcherSettings.load",
            return_value=PatcherSettings(enable_matching=False),
        )
        mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state(concurrency=10, debug=True)

        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["concurrency"] == 10
        assert call_kwargs["debug"] is True
        assert call_kwargs["enable_installomator"] is False  # enable_matching was False

    def test_ui_config_defaults_passed_when_unset(self, mocker):
        """With no saved UI settings, model defaults flow through as ui_config."""
        mocker.patch(
            "src.patcher.core.patcher_client.PatcherSettings.load",
            return_value=PatcherSettings(),
        )
        mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state()

        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["ui_config"]["header_text"] == "Default header text"


class TestExport:
    @pytest.mark.asyncio
    async def test_delegates_to_data_export_with_threaded_params(self, patcher):
        patcher.data.export = AsyncMock(return_value={"pdf": "/tmp/out.pdf"})

        result = await patcher.export(
            ["titles"],
            output_dir="/tmp",
            formats={"pdf"},
            report_title="Q2 Patch Report",
            date_format="%Y-%m-%d",
            header_color="#ff0000",
        )

        patcher.data.export.assert_awaited_once_with(
            patch_titles=["titles"],
            output_dir="/tmp",
            report_title="Q2 Patch Report",
            analysis=False,
            date_format="%Y-%m-%d",
            formats={"pdf"},
            header_color="#ff0000",
            device_reports=None,
        )
        assert result == {"pdf": "/tmp/out.pdf"}

    @pytest.mark.asyncio
    async def test_default_report_title_falls_back_to_ui_config(self, patcher):
        """When report_title isn't passed, use ui_config['header_text']."""
        patcher.data.export = AsyncMock(return_value={})
        patcher.ui_config = {"header_text": "Custom Header"}

        await patcher.export(["titles"], output_dir="/tmp")

        call_kwargs = patcher.data.export.await_args.kwargs
        assert call_kwargs["report_title"] == "Custom Header"

    @pytest.mark.asyncio
    async def test_default_report_title_when_ui_config_missing_header(self, patcher):
        """When ui_config lacks header_text, fall back to the literal default."""
        patcher.data.export = AsyncMock(return_value={})
        patcher.ui_config = {}

        await patcher.export(["titles"], output_dir="/tmp")

        call_kwargs = patcher.data.export.await_args.kwargs
        assert call_kwargs["report_title"] == "Patch Report"

    @pytest.mark.asyncio
    async def test_formats_optional(self, patcher):
        """When formats isn't passed, DataManager.export's own default takes over (all four)."""
        patcher.data.export = AsyncMock(return_value={})

        await patcher.export(["titles"], output_dir="/tmp")

        call_kwargs = patcher.data.export.await_args.kwargs
        assert call_kwargs["formats"] is None
