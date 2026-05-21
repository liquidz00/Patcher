import pickle

import pandas as pd
import pytest
from src.patcher.core.analyze import TitleFilter, TrendAnalysis
from src.patcher.core.exceptions import PatcherError
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
