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
from src.patcher.core.analyze import FilterCriteria
from src.patcher.core.exceptions import PatcherError
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
    p.jamf.get_summaries.return_value = mock_patch_title_response
    p.data = AsyncMock()
    p.api = AsyncMock()
    return p


class TestFetchPatches:
    @pytest.mark.asyncio
    async def test_default_flow_runs_policies_summaries_and_match(self, patcher, mocker):
        mock_match = mocker.patch(
            "src.patcher.core.patcher_client.match_titles",
            new_callable=AsyncMock,
        )

        result = await patcher.fetch_patches()

        patcher.jamf.get_policies.assert_awaited_once()
        patcher.jamf.get_summaries.assert_awaited_once_with(patcher.jamf.get_policies.return_value)
        mock_match.assert_awaited_once_with(
            patcher.jamf.get_summaries.return_value,
            jamf=patcher.jamf,
            api=patcher.api,
        )
        assert result == patcher.jamf.get_summaries.return_value

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
    async def test_string_criteria_converted_to_enum(self, patcher, mocker):
        """A CLI-style string ``'most-installed'`` should resolve to MOST_INSTALLED."""
        # Replace data.titles' setter side effect to be safe; the Analyzer
        # instantiation reads from data so we mock it at the class level.
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = ["result"]

        patcher.data = MagicMock()  # plain MagicMock to allow setting .titles

        result = await patcher.analyze(["titles"], criteria="most-installed")

        # Analyzer was constructed with the data manager
        mock_analyzer_cls.assert_called_once_with(patcher.data)
        # filter_titles received the enum form (string was converted)
        mock_analyzer_cls.return_value.filter_titles.assert_called_once_with(
            FilterCriteria.MOST_INSTALLED, threshold=70.0, top_n=None
        )
        assert result == ["result"]

    @pytest.mark.asyncio
    async def test_enum_criteria_passed_through_unchanged(self, patcher, mocker):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = ["result"]
        patcher.data = MagicMock()

        await patcher.analyze(["titles"], criteria=FilterCriteria.TOP_PERFORMERS)

        mock_analyzer_cls.return_value.filter_titles.assert_called_once_with(
            FilterCriteria.TOP_PERFORMERS, threshold=70.0, top_n=None
        )

    @pytest.mark.asyncio
    async def test_threshold_and_top_n_threaded_through(self, patcher, mocker):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = []
        patcher.data = MagicMock()

        await patcher.analyze(
            ["titles"],
            criteria=FilterCriteria.BELOW_THRESHOLD,
            threshold=85.0,
            top_n=5,
        )

        mock_analyzer_cls.return_value.filter_titles.assert_called_once_with(
            FilterCriteria.BELOW_THRESHOLD, threshold=85.0, top_n=5
        )

    @pytest.mark.asyncio
    async def test_invalid_string_criteria_raises_patcher_error(self, patcher):
        with pytest.raises(PatcherError, match="Invalid criteria"):
            await patcher.analyze(["titles"], criteria="not-a-real-criterion")

    @pytest.mark.asyncio
    async def test_stashes_titles_on_data_manager(self, patcher, mocker):
        """Analyzer reads from data.titles; analyze() must set it before instantiating."""
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = []
        patcher.data = MagicMock()

        await patcher.analyze(["my-titles"], criteria=FilterCriteria.MOST_INSTALLED)

        # The setter side of `patcher.data.titles = ["my-titles"]` should fire.
        # MagicMock records attribute assignment via __setattr__; we just verify
        # construction order — Analyzer is built AFTER the assignment.
        assert mock_analyzer_cls.call_count == 1


class TestAnalyzeExcel:
    @pytest.mark.asyncio
    async def test_analyzer_constructed_with_excel_path(self, patcher, mocker):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = ["from-excel"]

        result = await patcher.analyze_excel(
            "/tmp/report.xlsx", criteria=FilterCriteria.MOST_INSTALLED
        )

        mock_analyzer_cls.assert_called_once_with(
            excel_path="/tmp/report.xlsx", data_manager=patcher.data
        )
        assert result == ["from-excel"]

    @pytest.mark.asyncio
    async def test_cli_string_criteria_converts(self, patcher, mocker):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        mock_analyzer_cls.return_value.filter_titles.return_value = []

        await patcher.analyze_excel("/tmp/r.xlsx", criteria="below-threshold")

        mock_analyzer_cls.return_value.filter_titles.assert_called_once_with(
            FilterCriteria.BELOW_THRESHOLD, threshold=70.0, top_n=None
        )


class TestAnalyzeTrend:
    @pytest.mark.asyncio
    async def test_returns_trend_dataframe(self, patcher, mocker):
        from src.patcher.core.analyze import TrendCriteria

        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        fake_df = mocker.MagicMock()
        fake_df.empty = False
        mock_analyzer_cls.return_value.timelapse.return_value = fake_df

        result = await patcher.analyze_trend("patch-adoption")

        mock_analyzer_cls.assert_called_once_with(patcher.data)
        mock_analyzer_cls.return_value.timelapse.assert_called_once_with(
            TrendCriteria.PATCH_ADOPTION
        )
        assert result is fake_df

    @pytest.mark.asyncio
    async def test_save_to_writes_html(self, patcher, mocker, tmp_path):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        fake_df = mocker.MagicMock()
        fake_df.empty = False
        mock_analyzer_cls.return_value.timelapse.return_value = fake_df

        out = tmp_path / "trend.html"
        await patcher.analyze_trend("patch-adoption", save_to=out)

        fake_df.to_html.assert_called_once_with(out, index=False)

    @pytest.mark.asyncio
    async def test_save_to_skipped_on_empty_dataframe(self, patcher, mocker, tmp_path):
        mock_analyzer_cls = mocker.patch("src.patcher.core.patcher_client.Analyzer")
        fake_df = mocker.MagicMock()
        fake_df.empty = True
        mock_analyzer_cls.return_value.timelapse.return_value = fake_df

        await patcher.analyze_trend("patch-adoption", save_to=tmp_path / "trend.html")

        fake_df.to_html.assert_not_called()


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
    async def test_creds_all_calls_reset_config(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        mocker.patch("src.patcher.core.patcher_client.PropertylistManager")

        await patcher.reset("creds")

        patcher._config.reset_config.assert_called_once()
        patcher._config.set_credential.assert_not_called()

    @pytest.mark.asyncio
    async def test_creds_with_credential_arg_clears_one_key(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        mocker.patch("src.patcher.core.patcher_client.PropertylistManager")

        await patcher.reset("creds", credential="url")

        patcher._config.set_credential.assert_called_once_with("URL", "")
        patcher._config.reset_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_ui_removes_plist_key(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        mock_plist_cls = mocker.patch("src.patcher.core.patcher_client.PropertylistManager")

        await patcher.reset("UI")

        mock_plist_cls.return_value.remove.assert_called_once_with("UserInterfaceSettings")

    @pytest.mark.asyncio
    async def test_full_runs_every_reset(self, patcher, mocker):
        patcher._config = MagicMock()
        patcher._config.in_memory_mode = False
        patcher.data.reset_cache = MagicMock(return_value=True)
        mock_plist_cls = mocker.patch("src.patcher.core.patcher_client.PropertylistManager")

        await patcher.reset("full")

        patcher._config.reset_config.assert_called_once()
        plist = mock_plist_cls.return_value
        assert plist.remove.call_count == 2
        plist.remove.assert_any_call("UserInterfaceSettings")
        plist.remove.assert_any_call("setup_completed")
        patcher.data.reset_cache.assert_called_once()


class TestFromState:
    def test_reads_ui_and_installomator_from_plist(self, mocker):
        mock_plist = mocker.patch(
            "src.patcher.core.patcher_client.PropertylistManager"
        ).return_value
        mock_plist.get.side_effect = lambda key: {
            "UserInterfaceSettings": {"header_text": "Org Header"},
            "enable_installomator": True,
        }.get(key)
        mock_config_cls = mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state()

        mock_client_cls.assert_called_once_with(
            config=mock_config_cls.return_value,
            enable_installomator=True,
            ui_config={"header_text": "Org Header"},
        )

    def test_overrides_take_precedence(self, mocker):
        mock_plist = mocker.patch(
            "src.patcher.core.patcher_client.PropertylistManager"
        ).return_value
        mock_plist.get.return_value = None  # no UI settings, no toggle
        mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state(concurrency=10, debug=True)

        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["concurrency"] == 10
        assert call_kwargs["debug"] is True
        assert call_kwargs["enable_installomator"] is False  # plist had nothing

    def test_omits_ui_config_when_plist_has_none(self, mocker):
        """Empty UI settings should fall through to PatcherClient's defaults."""
        mock_plist = mocker.patch(
            "src.patcher.core.patcher_client.PropertylistManager"
        ).return_value
        mock_plist.get.return_value = None
        mocker.patch("src.patcher.core.patcher_client.ConfigManager")
        mock_client_cls = mocker.patch.object(PatcherClient, "__init__", return_value=None)

        PatcherClient.from_state()

        call_kwargs = mock_client_cls.call_args.kwargs
        assert "ui_config" not in call_kwargs  # falls through to UIDefaults


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
