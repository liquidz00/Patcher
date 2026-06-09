import os
import pickle
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from src.patcher.core.analyze import Diff, TitleFilter, TrendAnalysis
from src.patcher.core.data_manager import DataManager
from src.patcher.core.exceptions import PatcherError
from src.patcher.core.models.cask import CaskMatch
from src.patcher.core.models.label import Label
from src.patcher.core.models.patch import PatchTitle

pytestmark = pytest.mark.unit


def make_title(
    title: str,
    *,
    hosts_patched: int = 0,
    missing_patch: int = 0,
    released: str = "Jan 01 2024",
    latest_version: str = "1.0.0",
    install_label: list[str] | None = None,
) -> PatchTitle:
    """Builder for PatchTitle test fixtures.

    ``completion_percent`` and ``total_hosts`` are derived by PatchTitle's
    model validator from ``hosts_patched`` and ``missing_patch``, so callers
    set those to express the percentage they want (e.g. 95/5 = 95%).
    """
    return PatchTitle(
        title=title,
        title_id=title.lower().replace(" ", "-"),
        released=released,
        hosts_patched=hosts_patched,
        missing_patch=missing_patch,
        latest_version=latest_version,
        install_label=install_label or [],
    )


@pytest.fixture
def sample_titles() -> list[PatchTitle]:
    return [
        make_title("Patch A", hosts_patched=50, missing_patch=10),  # ~83% complete, 60 hosts
        make_title("Patch B", hosts_patched=30, missing_patch=20),  # 60% complete, 50 hosts
        make_title("Patch C", hosts_patched=20, missing_patch=5),  # 80% complete, 25 hosts
    ]


class TestTitleFilterMethods:
    def test_most_installed_orders_by_total_hosts_desc(self, sample_titles):
        result = TitleFilter(sample_titles).most_installed()
        assert [t.title for t in result] == ["Patch A", "Patch B", "Patch C"]

    def test_least_installed_orders_by_total_hosts_asc(self, sample_titles):
        result = TitleFilter(sample_titles).least_installed()
        assert [t.title for t in result] == ["Patch C", "Patch B", "Patch A"]

    def test_top_n_caps_result(self, sample_titles):
        result = TitleFilter(sample_titles).most_installed(top_n=2)
        assert len(result) == 2
        assert [t.title for t in result] == ["Patch A", "Patch B"]

    def test_below_threshold_returns_all_matches_no_cap(self, sample_titles):
        # below 70% catches only Patch B
        result = TitleFilter(sample_titles).below_threshold(threshold=70.0)
        assert [t.title for t in result] == ["Patch B"]

    def test_below_threshold_signature_has_no_top_n(self):
        import inspect

        sig = inspect.signature(TitleFilter.below_threshold)
        assert "top_n" not in sig.parameters
        assert "threshold" in sig.parameters

    def test_zero_completion_returns_only_zero_titles(self):
        titles = [
            make_title("Done", hosts_patched=5, missing_patch=0),
            make_title("Stale", hosts_patched=0, missing_patch=5),
        ]
        result = TitleFilter(titles).zero_completion()
        assert [t.title for t in result] == ["Stale"]

    def test_zero_completion_signature_has_no_top_n_or_threshold(self):
        import inspect

        sig = inspect.signature(TitleFilter.zero_completion)
        assert list(sig.parameters) == ["self"]

    def test_top_performers_filters_above_90(self):
        titles = [
            make_title("Almost", hosts_patched=89, missing_patch=11),  # 89%
            make_title("Yes", hosts_patched=95, missing_patch=5),  # 95%
            make_title("Way over", hosts_patched=99, missing_patch=1),  # 99%
        ]
        result = TitleFilter(titles).top_performers()
        assert [t.title for t in result] == ["Way over", "Yes"]

    def test_high_missing_filters_over_50pct_missing(self):
        # missing_patch > total_hosts * 0.5
        titles = [
            make_title("Bad", hosts_patched=1, missing_patch=9),  # 90% missing
            make_title("Mid", hosts_patched=6, missing_patch=4),  # 40% missing — excluded
        ]
        result = TitleFilter(titles).high_missing()
        assert [t.title for t in result] == ["Bad"]

    def test_installomator_keeps_titles_with_labels(self):
        label = Label(name="Firefox", installomator_label="firefox")
        titles = [
            make_title("With label", install_label=[label]),
            make_title("Without", install_label=[]),
        ]
        result = TitleFilter(titles).installomator()
        assert [t.title for t in result] == ["With label"]


class TestTitleFilterApply:
    """The kebab-case-string dispatch used by CLI and PatcherClient.analyze."""

    def test_kebab_case_string_dispatches_to_method(self, sample_titles):
        result = TitleFilter.apply(sample_titles, "most-installed")
        assert [t.title for t in result] == ["Patch A", "Patch B", "Patch C"]

    def test_apply_passes_only_accepted_kwargs(self, sample_titles):
        # threshold is irrelevant to most_installed; top_n is applied.
        result = TitleFilter.apply(sample_titles, "most-installed", threshold=99.0, top_n=1)
        assert len(result) == 1
        assert result[0].title == "Patch A"

    def test_apply_threshold_for_below_threshold(self, sample_titles):
        # top_n is ignored by below_threshold; threshold drives the filter.
        result = TitleFilter.apply(sample_titles, "below-threshold", threshold=70.0, top_n=99)
        assert [t.title for t in result] == ["Patch B"]

    def test_unknown_criterion_raises(self, sample_titles):
        with pytest.raises(PatcherError, match="Invalid criteria"):
            TitleFilter.apply(sample_titles, "not-a-real-criterion")

    def test_private_method_not_dispatchable(self, sample_titles):
        with pytest.raises(PatcherError, match="Invalid criteria"):
            TitleFilter.apply(sample_titles, "-cap")

    def test_apply_helper_method_not_dispatchable(self, sample_titles):
        # `apply` itself shouldn't be reachable via apply()
        with pytest.raises(PatcherError, match="Invalid criteria"):
            TitleFilter.apply(sample_titles, "apply")


class TestTitleFilterCriteria:
    def test_criteria_lists_kebab_case_names(self):
        names = TitleFilter.criteria()
        assert "most-installed" in names
        assert "below-threshold" in names
        assert "zero-completion" in names
        # helpers and dunders shouldn't appear
        assert "apply" not in names
        assert "criteria" not in names


class TestTrendAnalysis:
    @pytest.fixture
    def two_datasets(self, tmp_path) -> list:
        # Two pre-loaded DataFrames covering two snapshots.
        snap1 = pd.DataFrame(
            {
                "Title": ["Patch A", "Patch B"],
                "Released": ["Jan 01 2024", "Jan 15 2024"],
                "Completion Percent": [80.0, 50.0],
            }
        )
        snap2 = pd.DataFrame(
            {
                "Title": ["Patch A", "Patch B"],
                "Released": ["Jan 01 2024", "Jan 15 2024"],
                "Completion Percent": [90.0, 75.0],
            }
        )
        return [snap1, snap2]

    def test_requires_at_least_two_datasets(self):
        with pytest.raises(PatcherError, match="Insufficient data"):
            TrendAnalysis([])

        with pytest.raises(PatcherError, match="Insufficient data"):
            TrendAnalysis([pd.DataFrame()])

    def test_patch_adoption_averages_completion(self, two_datasets):
        df = TrendAnalysis(two_datasets).patch_adoption()
        assert list(df.columns) == ["Title", "Average Completion", "Most Recent Release"]
        # Patch A: avg(80, 90) = 85.00%
        a_row = df[df["Title"] == "Patch A"].iloc[0]
        assert a_row["Average Completion"] == "85.00%"

    def test_release_frequency_counts_distinct_dates(self, two_datasets):
        df = TrendAnalysis(two_datasets).release_frequency()
        assert list(df.columns) == ["Title", "Release Count"]
        assert df[df["Title"] == "Patch A"]["Release Count"].iloc[0] == 1

    def test_completion_trends_keyed_by_date(self, two_datasets):
        df = TrendAnalysis(two_datasets).completion_trends()
        assert list(df.columns) == ["Release Date", "Title", "Average Completion"]

    def test_apply_dispatches_by_kebab_case(self, two_datasets):
        df = TrendAnalysis.apply(two_datasets, "patch-adoption")
        assert not df.empty

    def test_apply_unknown_criterion_raises(self, two_datasets):
        with pytest.raises(PatcherError, match="Invalid criteria"):
            TrendAnalysis.apply(two_datasets, "not-real")

    def test_sort_by_unknown_column_raises(self, two_datasets):
        with pytest.raises(PatcherError, match="Invalid sorting"):
            TrendAnalysis(two_datasets).patch_adoption(sort_by="nonexistent")

    def test_reads_pkl_files(self, tmp_path):
        df1 = pd.DataFrame(
            {"Title": ["A"], "Released": ["Jan 01 2024"], "Completion Percent": [50.0]}
        )
        df2 = pd.DataFrame(
            {"Title": ["A"], "Released": ["Jan 01 2024"], "Completion Percent": [75.0]}
        )
        p1 = tmp_path / "snap1.pkl"
        p2 = tmp_path / "snap2.pkl"
        with open(p1, "wb") as f:
            pickle.dump(df1, f)
        with open(p2, "wb") as f:
            pickle.dump(df2, f)

        df = TrendAnalysis([p1, p2]).patch_adoption()
        assert df[df["Title"] == "A"]["Average Completion"].iloc[0] == "62.50%"

    def test_unsupported_file_type_raises(self, tmp_path):
        bogus1 = tmp_path / "snap.csv"
        bogus1.write_text("not-supported")
        bogus2 = tmp_path / "snap2.csv"
        bogus2.write_text("not-supported")
        with pytest.raises(PatcherError, match="Unsupported dataset file type"):
            TrendAnalysis([bogus1, bogus2])

    def test_from_cache_uses_data_manager_cached_files(self, two_datasets, mocker):
        # Patch get_cached_files to return our pre-built DataFrames as datasets.
        dm = mocker.MagicMock()
        dm.get_cached_files.return_value = two_datasets
        instance = TrendAnalysis.from_cache(dm)
        df = instance.patch_adoption()
        assert not df.empty


class TestImpactWeightedRisk:
    def test_orders_by_missing_times_age_descending(self):
        # Newer, lots missing vs older, few missing. With age multiplier, the
        # older one with even modest missing-patch count usually wins.
        recent_huge = make_title(
            "Recent Huge",
            hosts_patched=10,
            missing_patch=100,
            released=(datetime.now() - timedelta(days=2)).strftime("%b %d %Y"),
        )
        old_modest = make_title(
            "Old Modest",
            hosts_patched=10,
            missing_patch=10,
            released=(datetime.now() - timedelta(days=365)).strftime("%b %d %Y"),
        )
        result = TitleFilter([recent_huge, old_modest]).impact_weighted_risk()
        # 10*365 = 3650 vs 100*2 = 200 -> Old Modest first.
        assert [t.title for t in result] == ["Old Modest", "Recent Huge"]

    def test_top_n_caps_result(self):
        titles = [
            make_title(
                f"P{i}",
                hosts_patched=1,
                missing_patch=i + 1,
                released=(datetime.now() - timedelta(days=30 * (i + 1))).strftime("%b %d %Y"),
            )
            for i in range(5)
        ]
        result = TitleFilter(titles).impact_weighted_risk(top_n=2)
        assert len(result) == 2

    def test_unparseable_released_skipped_not_raised(self):
        good = make_title(
            "Good",
            hosts_patched=10,
            missing_patch=5,
            released=(datetime.now() - timedelta(days=10)).strftime("%b %d %Y"),
        )
        bad = make_title("Bad", hosts_patched=10, missing_patch=5, released="not a date")
        result = TitleFilter([good, bad]).impact_weighted_risk()
        assert [t.title for t in result] == ["Good"]


class TestCoverageGaps:
    def test_only_uncovered_titles_returned(self):
        label = Label(name="Firefox", installomator_label="firefox")
        cask = CaskMatch(name="Slack", token="slack")
        covered_label = make_title(
            "Covered by Label", hosts_patched=10, missing_patch=5, install_label=[label]
        )
        covered_cask = make_title("Covered by Cask", hosts_patched=10, missing_patch=5)
        covered_cask.homebrew_cask = [cask]
        gap = make_title("Gap", hosts_patched=10, missing_patch=20)
        result = TitleFilter([covered_label, covered_cask, gap]).coverage_gaps()
        assert [t.title for t in result] == ["Gap"]

    def test_sorts_by_missing_patch_desc(self):
        small_gap = make_title("Small", hosts_patched=10, missing_patch=3)
        big_gap = make_title("Big", hosts_patched=1, missing_patch=99)
        mid_gap = make_title("Mid", hosts_patched=5, missing_patch=15)
        result = TitleFilter([small_gap, big_gap, mid_gap]).coverage_gaps()
        assert [t.title for t in result] == ["Big", "Mid", "Small"]

    def test_top_n_caps_result(self):
        titles = [make_title(f"P{i}", hosts_patched=1, missing_patch=i + 1) for i in range(5)]
        result = TitleFilter(titles).coverage_gaps(top_n=2)
        assert len(result) == 2

    def test_empty_input_returns_empty(self):
        assert TitleFilter([]).coverage_gaps() == []

    def test_all_covered_returns_empty(self):
        label = Label(name="Firefox", installomator_label="firefox")
        covered = make_title("All Set", hosts_patched=10, missing_patch=5, install_label=[label])
        assert TitleFilter([covered]).coverage_gaps() == []


class TestWherePreFilter:
    def test_min_compliance_filters(self, sample_titles):
        # Patch A ~83%, Patch B 60%, Patch C 80% -> >=80 keeps A and C.
        result = TitleFilter(sample_titles).where(min_compliance=80.0)
        kept = sorted(t.title for t in result._titles)
        assert kept == ["Patch A", "Patch C"]

    def test_min_hosts_filters(self, sample_titles):
        # Patch A 60, Patch B 50, Patch C 25 -> >=50 keeps A and B.
        result = TitleFilter(sample_titles).where(min_hosts=50)
        kept = sorted(t.title for t in result._titles)
        assert kept == ["Patch A", "Patch B"]

    def test_released_after_filters(self):
        old = make_title("Old", hosts_patched=1, missing_patch=1, released="Jan 01 2024")
        new = make_title("New", hosts_patched=1, missing_patch=1, released="Jun 01 2025")
        result = TitleFilter([old, new]).where(released_after="2025-01-01")
        assert [t.title for t in result._titles] == ["New"]

    def test_released_after_skips_unparseable(self):
        good = make_title("Good", hosts_patched=1, missing_patch=1, released="Jun 01 2025")
        bad = make_title("Bad", hosts_patched=1, missing_patch=1, released="garbage")
        result = TitleFilter([good, bad]).where(released_after="2025-01-01")
        assert [t.title for t in result._titles] == ["Good"]

    def test_combined_kwargs_compose_as_and(self, sample_titles):
        # min_compliance=70 keeps A and C; min_hosts=50 keeps A and B; AND keeps only A.
        result = TitleFilter(sample_titles).where(min_compliance=70.0, min_hosts=50)
        assert [t.title for t in result._titles] == ["Patch A"]

    def test_returns_new_instance_does_not_mutate_caller(self, sample_titles):
        original = TitleFilter(sample_titles)
        original_ids = [id(t) for t in original._titles]
        filtered = original.where(min_compliance=70.0)
        assert filtered is not original
        # caller's title list unchanged
        assert [id(t) for t in original._titles] == original_ids
        assert len(original._titles) == 3

    def test_no_kwargs_returns_copy_with_all_titles(self, sample_titles):
        result = TitleFilter(sample_titles).where()
        assert [t.title for t in result._titles] == [t.title for t in sample_titles]

    def test_invalid_iso_date_raises(self, sample_titles):
        with pytest.raises(PatcherError, match="Invalid ISO date"):
            TitleFilter(sample_titles).where(released_after="not-a-date")

    def test_apply_routes_through_where(self, sample_titles):
        # where keeps only Patch A; most-installed then sorts what's left.
        result = TitleFilter.apply(
            sample_titles,
            "most-installed",
            where={"min_compliance": 70.0, "min_hosts": 50},
        )
        assert [t.title for t in result] == ["Patch A"]

    def test_apply_unknown_where_kwarg_raises(self, sample_titles):
        with pytest.raises(PatcherError, match="Unknown pre-filter kwargs"):
            TitleFilter.apply(sample_titles, "most-installed", where={"bogus": 1})


class TestTitleFilterCriteriaIncludesNewMethods:
    def test_includes_impact_weighted_risk(self):
        assert "impact-weighted-risk" in TitleFilter.criteria()

    def test_includes_coverage_gaps(self):
        assert "coverage-gaps" in TitleFilter.criteria()

    def test_where_is_not_a_criterion(self):
        # `where` is a chaining helper, not a dispatchable filter.
        assert "where" not in TitleFilter.criteria()


def _dump_trend_pkl(path, *, titles, mtime):
    """Pickle a snapshot DataFrame and set its mtime."""
    df = pd.DataFrame([t.model_dump() for t in titles])
    with open(path, "wb") as f:
        pickle.dump(df, f)
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))
    return path


class TestTimeToPatch:
    def test_titles_that_cross_threshold_measured(self, tmp_path):
        # Title released Jan 01 2024; crosses 80% in snapshot dated Jan 11 (10 days).
        release = "Jan 01 2024"
        snap1_titles = [make_title("Slow", hosts_patched=5, missing_patch=5, released=release)]
        snap2_titles = [make_title("Slow", hosts_patched=9, missing_patch=1, released=release)]
        p1 = _dump_trend_pkl(
            tmp_path / "snap1.pkl", titles=snap1_titles, mtime=datetime(2024, 1, 5, 12, 0, 0)
        )
        p2 = _dump_trend_pkl(
            tmp_path / "snap2.pkl", titles=snap2_titles, mtime=datetime(2024, 1, 11, 12, 0, 0)
        )
        df = TrendAnalysis([p1, p2]).time_to_patch(threshold=80.0)
        assert list(df.columns) == [
            "Title",
            "Avg Days to Threshold",
            "Sample Size",
            "Threshold",
        ]
        row = df[df["Title"] == "Slow"].iloc[0]
        assert row["Sample Size"] == 1
        assert row["Threshold"] == 80.0
        # 10 days from release (Jan 01) to first crossing snapshot (Jan 11).
        assert row["Avg Days to Threshold"] == 10.0

    def test_titles_never_crossing_threshold_excluded(self, tmp_path):
        release = "Jan 01 2024"
        snap1_titles = [
            make_title("Never", hosts_patched=1, missing_patch=9, released=release),
            make_title("Yes", hosts_patched=9, missing_patch=1, released=release),
        ]
        snap2_titles = [
            make_title("Never", hosts_patched=2, missing_patch=8, released=release),
            make_title("Yes", hosts_patched=10, missing_patch=0, released=release),
        ]
        p1 = _dump_trend_pkl(
            tmp_path / "s1.pkl", titles=snap1_titles, mtime=datetime(2024, 1, 5, 12, 0, 0)
        )
        p2 = _dump_trend_pkl(
            tmp_path / "s2.pkl", titles=snap2_titles, mtime=datetime(2024, 1, 11, 12, 0, 0)
        )
        df = TrendAnalysis([p1, p2]).time_to_patch(threshold=80.0)
        titles = set(df["Title"].tolist())
        assert "Yes" in titles
        assert "Never" not in titles

    def test_single_snapshot_case_via_two_identical(self, tmp_path):
        # The class requires >=2 datasets; produce two snapshots where nothing
        # ever crosses the threshold to assert an empty result.
        release = "Jan 01 2024"
        snap_titles = [make_title("Low", hosts_patched=1, missing_patch=9, released=release)]
        p1 = _dump_trend_pkl(
            tmp_path / "s1.pkl", titles=snap_titles, mtime=datetime(2024, 1, 5, 12, 0, 0)
        )
        p2 = _dump_trend_pkl(
            tmp_path / "s2.pkl", titles=snap_titles, mtime=datetime(2024, 1, 11, 12, 0, 0)
        )
        df = TrendAnalysis([p1, p2]).time_to_patch(threshold=99.0)
        assert df.empty
        assert list(df.columns) == [
            "Title",
            "Avg Days to Threshold",
            "Sample Size",
            "Threshold",
        ]


class TestStaleApps:
    def test_identifies_stale_when_version_and_completion_unchanged(self, tmp_path):
        release = "Jan 01 2024"
        snaps = []
        # Three snapshots, same version, same completion (50%).
        for i, mt in enumerate(
            [
                datetime(2024, 1, 1, 12, 0, 0),
                datetime(2024, 1, 8, 12, 0, 0),
                datetime(2024, 1, 15, 12, 0, 0),
            ]
        ):
            titles = [
                make_title(
                    "Stuck",
                    hosts_patched=5,
                    missing_patch=5,
                    latest_version="1.0.0",
                    released=release,
                )
            ]
            snaps.append(_dump_trend_pkl(tmp_path / f"snap{i}.pkl", titles=titles, mtime=mt))
        df = TrendAnalysis(snaps).stale_apps(min_snapshots=3)
        assert list(df.columns) == [
            "Title",
            "Latest Version",
            "Completion %",
            "Days Stale",
        ]
        assert len(df) == 1
        row = df.iloc[0]
        assert row["Title"] == "Stuck"
        assert row["Latest Version"] == "1.0.0"
        assert row["Completion %"] == 50.0
        assert row["Days Stale"] == 14

    def test_ignores_titles_with_fewer_snapshots(self, tmp_path):
        release = "Jan 01 2024"
        titles_a = [
            make_title(
                "Both", hosts_patched=5, missing_patch=5, latest_version="1.0.0", released=release
            )
        ]
        titles_b = [
            make_title(
                "Both", hosts_patched=5, missing_patch=5, latest_version="1.0.0", released=release
            ),
            make_title(
                "Late", hosts_patched=5, missing_patch=5, latest_version="2.0.0", released=release
            ),
        ]
        titles_c = [
            make_title(
                "Both", hosts_patched=5, missing_patch=5, latest_version="1.0.0", released=release
            ),
            make_title(
                "Late", hosts_patched=5, missing_patch=5, latest_version="2.0.0", released=release
            ),
        ]
        p1 = _dump_trend_pkl(tmp_path / "s1.pkl", titles=titles_a, mtime=datetime(2024, 1, 1))
        p2 = _dump_trend_pkl(tmp_path / "s2.pkl", titles=titles_b, mtime=datetime(2024, 1, 8))
        p3 = _dump_trend_pkl(tmp_path / "s3.pkl", titles=titles_c, mtime=datetime(2024, 1, 15))
        df = TrendAnalysis([p1, p2, p3]).stale_apps(min_snapshots=3)
        titles_in_result = set(df["Title"].tolist())
        assert "Both" in titles_in_result
        assert "Late" not in titles_in_result

    def test_ignores_titles_whose_version_moved(self, tmp_path):
        release = "Jan 01 2024"
        snaps = []
        for i, (mt, version) in enumerate(
            [
                (datetime(2024, 1, 1), "1.0.0"),
                (datetime(2024, 1, 8), "1.0.1"),
                (datetime(2024, 1, 15), "1.0.1"),
            ]
        ):
            titles = [
                make_title(
                    "Moving",
                    hosts_patched=5,
                    missing_patch=5,
                    latest_version=version,
                    released=release,
                )
            ]
            snaps.append(_dump_trend_pkl(tmp_path / f"s{i}.pkl", titles=titles, mtime=mt))
        df = TrendAnalysis(snaps).stale_apps(min_snapshots=3)
        assert df.empty

    def test_no_stale_returns_empty_not_raise(self, tmp_path):
        release = "Jan 01 2024"
        snaps = []
        # Completion changes each snapshot -> never stale.
        for i, (mt, hp) in enumerate(
            [
                (datetime(2024, 1, 1), 5),
                (datetime(2024, 1, 8), 6),
                (datetime(2024, 1, 15), 7),
            ]
        ):
            titles = [
                make_title(
                    "Progressing",
                    hosts_patched=hp,
                    missing_patch=10 - hp,
                    latest_version="1.0.0",
                    released=release,
                )
            ]
            snaps.append(_dump_trend_pkl(tmp_path / f"s{i}.pkl", titles=titles, mtime=mt))
        df = TrendAnalysis(snaps).stale_apps(min_snapshots=3)
        assert df.empty
        assert list(df.columns) == [
            "Title",
            "Latest Version",
            "Completion %",
            "Days Stale",
        ]


class TestTrendAnalysisCriteriaIncludesNewMethods:
    def test_includes_time_to_patch(self):
        assert "time-to-patch" in TrendAnalysis.criteria()

    def test_includes_stale_apps(self):
        assert "stale-apps" in TrendAnalysis.criteria()


class TestDiff:
    """Pairwise snapshot comparison."""

    def _dump_snapshot(
        self, tmp_path, name: str, titles: list[PatchTitle], mtime: datetime | None = None
    ):
        """Write a pickle file matching the cache layout and optionally set mtime."""
        df = pd.DataFrame([t.model_dump() for t in titles])
        path = tmp_path / f"patch_data_{name}.pkl"
        with open(path, "wb") as f:
            pickle.dump(df, f)
        if mtime is not None:
            ts = mtime.timestamp()
            os.utime(path, (ts, ts))
        return path

    def test_added_titles_detected(self):
        before = [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        after = [
            make_title("Patch A", hosts_patched=50, missing_patch=10),
            make_title("Patch B", hosts_patched=30, missing_patch=20),
        ]
        result = Diff(before, after).compute()
        assert len(result.added) == 1
        assert result.added[0].title == "Patch B"
        assert result.removed == []

    def test_removed_titles_detected(self):
        before = [
            make_title("Patch A", hosts_patched=50, missing_patch=10),
            make_title("Patch B", hosts_patched=30, missing_patch=20),
        ]
        after = [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        result = Diff(before, after).compute()
        assert result.added == []
        assert len(result.removed) == 1
        assert result.removed[0].title == "Patch B"

    def test_completion_delta_computed(self):
        before = [make_title("Patch A", hosts_patched=50, missing_patch=50)]  # 50%
        after = [make_title("Patch A", hosts_patched=80, missing_patch=20)]  # 80%
        result = Diff(before, after).compute()
        assert len(result.changed) == 1
        change = result.changed[0]
        assert change.from_completion_percent == 50.0
        assert change.to_completion_percent == 80.0
        assert change.completion_delta == 30.0
        assert result.avg_completion_delta == 30.0

    def test_version_bump_flagged(self):
        before = [make_title("Firefox", hosts_patched=50, missing_patch=10, latest_version="124.0")]
        after = [make_title("Firefox", hosts_patched=50, missing_patch=10, latest_version="125.0")]
        result = Diff(before, after).compute()
        assert len(result.changed) == 1
        assert result.changed[0].version_changed is True
        assert result.changed[0].from_latest_version == "124.0"
        assert result.changed[0].to_latest_version == "125.0"
        assert len(result.version_bumps) == 1

    def test_unchanged_titles_counted_not_listed(self):
        titles = [
            make_title("Patch A", hosts_patched=50, missing_patch=10),
            make_title("Patch B", hosts_patched=30, missing_patch=20),
            make_title("Patch C", hosts_patched=20, missing_patch=5),
        ]
        result = Diff(titles, titles).compute()
        assert result.unchanged_count == 3
        assert result.changed == []
        assert result.added == []
        assert result.removed == []

    def test_identical_snapshots_produce_empty_diff(self):
        titles = [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        result = Diff(titles, titles).compute()
        assert result.added == []
        assert result.removed == []
        assert result.changed == []
        assert result.unchanged_count == 1
        assert result.avg_completion_delta is None

    def test_labels_default_to_describe(self):
        titles = [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        result = Diff(titles, titles).compute()
        assert result.from_label == "live"
        assert result.to_label == "live"

    def test_custom_labels_override_default(self):
        titles = [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        result = Diff(titles, titles, from_label="cached", to_label="fresh").compute()
        assert result.from_label == "cached"
        assert result.to_label == "fresh"

    def test_accepts_dataframe_inputs(self):
        before_df = pd.DataFrame(
            [make_title("Patch A", hosts_patched=50, missing_patch=10).model_dump()]
        )
        after_df = pd.DataFrame(
            [make_title("Patch A", hosts_patched=80, missing_patch=20).model_dump()]
        )
        result = Diff(before_df, after_df).compute()
        assert len(result.changed) == 1
        assert result.from_label == "dataframe"

    def test_accepts_path_inputs(self, tmp_path):
        before_path = self._dump_snapshot(
            tmp_path, "before", [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        )
        after_path = self._dump_snapshot(
            tmp_path, "after", [make_title("Patch A", hosts_patched=80, missing_patch=20)]
        )
        result = Diff(before_path, after_path).compute()
        assert len(result.changed) == 1
        assert result.from_label.startswith("snapshot-")
        assert result.to_label.startswith("snapshot-")

    def test_raises_when_title_id_missing(self):
        # DataFrame without the required column
        bad = pd.DataFrame([{"title": "Patch A", "completion_percent": 50}])
        ok = pd.DataFrame([make_title("Patch A", hosts_patched=50, missing_patch=10).model_dump()])
        with pytest.raises(PatcherError, match="title_id"):
            Diff(bad, ok).compute()

    def test_from_cache_picks_two_most_recent(self, tmp_path):
        old = self._dump_snapshot(
            tmp_path,
            "old",
            [make_title("Patch A", hosts_patched=50, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=10),
        )
        middle = self._dump_snapshot(
            tmp_path,
            "middle",
            [make_title("Patch A", hosts_patched=60, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=5),
        )
        recent = self._dump_snapshot(
            tmp_path,
            "recent",
            [make_title("Patch A", hosts_patched=70, missing_patch=10)],
            mtime=datetime.now() - timedelta(hours=1),
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        result = Diff.from_cache(dm).compute()
        # `from` should be middle, `to` should be recent
        assert "middle" not in result.from_label  # labels are mtime-derived, not name-derived
        change = result.changed[0]
        assert change.from_hosts_patched == 60
        assert change.to_hosts_patched == 70

    def test_from_cache_raises_when_no_snapshots(self, tmp_path):
        dm = DataManager()
        dm.cache_dir = tmp_path
        with pytest.raises(PatcherError, match="No cached snapshots"):
            Diff.from_cache(dm)

    def test_from_cache_raises_when_only_one_snapshot_and_no_between(self, tmp_path):
        only = self._dump_snapshot(
            tmp_path, "only", [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        with pytest.raises(PatcherError, match="at least 2"):
            Diff.from_cache(dm)

    def test_from_cache_all_time_uses_earliest(self, tmp_path):
        old = self._dump_snapshot(
            tmp_path,
            "old",
            [make_title("Patch A", hosts_patched=50, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=30),
        )
        middle = self._dump_snapshot(
            tmp_path,
            "middle",
            [make_title("Patch A", hosts_patched=60, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=10),
        )
        recent = self._dump_snapshot(
            tmp_path,
            "recent",
            [make_title("Patch A", hosts_patched=70, missing_patch=10)],
            mtime=datetime.now() - timedelta(hours=1),
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        result = Diff.from_cache(dm, all_time=True).compute()
        change = result.changed[0]
        assert change.from_hosts_patched == 50  # earliest
        assert change.to_hosts_patched == 70  # most-recent

    def test_from_cache_since_filters_window(self, tmp_path):
        outside = self._dump_snapshot(
            tmp_path,
            "outside",
            [make_title("Patch A", hosts_patched=50, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=60),
        )
        inside_old = self._dump_snapshot(
            tmp_path,
            "inside_old",
            [make_title("Patch A", hosts_patched=60, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=10),
        )
        inside_new = self._dump_snapshot(
            tmp_path,
            "inside_new",
            [make_title("Patch A", hosts_patched=70, missing_patch=10)],
            mtime=datetime.now() - timedelta(hours=1),
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        # 30-day window: should pick inside_old as `from`, inside_new as `to`
        result = Diff.from_cache(dm, since=timedelta(days=30)).compute()
        change = result.changed[0]
        assert change.from_hosts_patched == 60
        assert change.to_hosts_patched == 70

    def test_from_cache_since_raises_when_no_snapshots_in_window(self, tmp_path):
        old1 = self._dump_snapshot(
            tmp_path,
            "old1",
            [make_title("Patch A", hosts_patched=50, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=60),
        )
        old2 = self._dump_snapshot(
            tmp_path,
            "old2",
            [make_title("Patch A", hosts_patched=60, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=50),
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        with pytest.raises(PatcherError, match="No cached snapshots in the requested window"):
            Diff.from_cache(dm, since=timedelta(days=7))

    def test_from_cache_between_picks_closest(self, tmp_path):
        s1 = self._dump_snapshot(
            tmp_path,
            "s1",
            [make_title("Patch A", hosts_patched=10, missing_patch=10)],
            mtime=datetime(2026, 5, 17, 12, 0, 0),
        )
        s2 = self._dump_snapshot(
            tmp_path,
            "s2",
            [make_title("Patch A", hosts_patched=20, missing_patch=10)],
            mtime=datetime(2026, 5, 19, 12, 0, 0),
        )
        s3 = self._dump_snapshot(
            tmp_path,
            "s3",
            [make_title("Patch A", hosts_patched=30, missing_patch=10)],
            mtime=datetime(2026, 5, 21, 12, 0, 0),
        )
        dm = DataManager()
        dm.cache_dir = tmp_path
        result = Diff.from_cache(
            dm,
            between=(date(2026, 5, 17), date(2026, 5, 21)),
        ).compute()
        change = result.changed[0]
        assert change.from_hosts_patched == 10
        assert change.to_hosts_patched == 30

    def test_live_vs_cache_uses_most_recent_default(self, tmp_path):
        cached = self._dump_snapshot(
            tmp_path, "cached", [make_title("Patch A", hosts_patched=50, missing_patch=10)]
        )
        live = [make_title("Patch A", hosts_patched=70, missing_patch=10)]
        dm = DataManager()
        dm.cache_dir = tmp_path
        result = Diff.live_vs_cache(live, dm).compute()
        assert result.to_label == "live"
        change = result.changed[0]
        assert change.from_hosts_patched == 50
        assert change.to_hosts_patched == 70

    def test_live_vs_cache_all_time(self, tmp_path):
        old = self._dump_snapshot(
            tmp_path,
            "old",
            [make_title("Patch A", hosts_patched=10, missing_patch=10)],
            mtime=datetime.now() - timedelta(days=30),
        )
        recent = self._dump_snapshot(
            tmp_path,
            "recent",
            [make_title("Patch A", hosts_patched=50, missing_patch=10)],
            mtime=datetime.now() - timedelta(hours=1),
        )
        live = [make_title("Patch A", hosts_patched=70, missing_patch=10)]
        dm = DataManager()
        dm.cache_dir = tmp_path
        result = Diff.live_vs_cache(live, dm, all_time=True).compute()
        change = result.changed[0]
        assert change.from_hosts_patched == 10  # earliest
        assert change.to_hosts_patched == 70  # live

    def test_live_vs_cache_raises_when_empty(self, tmp_path):
        dm = DataManager()
        dm.cache_dir = tmp_path
        with pytest.raises(PatcherError, match="No cached snapshots"):
            Diff.live_vs_cache([make_title("Patch A", hosts_patched=50, missing_patch=10)], dm)
