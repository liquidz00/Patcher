from unittest.mock import patch

import pandas as pd
import pytest
from src.patcher.client.analyze import Analyzer, FilterCriteria
from src.patcher.models.patch import PatchTitle

# Mock DataFrame for testing
mock_data = {
    "Title": ["Patch A", "Patch B", "Patch C"],
    "Title Id": ["0", "1", "2"],
    "Released": ["2022-01-01", "2023-01-01", "2023-12-01"],
    "Hosts Patched": [50, 30, 20],
    "Missing Patch": [10, 20, 5],
    "Latest Version": ["1.0.0", "2.0.0", "3.0.0"],
    "Total Hosts": [60, 50, 25],
}

mock_df = pd.DataFrame(mock_data)


@pytest.fixture
def mock_analyzer(tmp_path, mock_data_manager):
    """Fixture to initialize Analyzer with a temporary file."""
    test_excel_path = tmp_path / "test.xlsx"
    mock_df.to_excel(test_excel_path, index=False)
    return Analyzer(excel_path=test_excel_path, data_manager=mock_data_manager)


def test_patch_title_calculation():
    """Test the PatchTitle model's completion percentage calculation."""
    patch_title = PatchTitle(
        title="Patch A",
        title_id="0",
        released="2022-01-01",
        hosts_patched=50,
        missing_patch=10,
        latest_version="1.0.0",
    )
    assert patch_title.total_hosts == 60
    assert patch_title.completion_percent == 83.33

    # Test with zero total hosts
    patch_title_zero = PatchTitle(
        title="Patch B",
        title_id="1",
        released="2023-01-01",
        hosts_patched=0,
        missing_patch=0,
        latest_version="2.0.0",
    )
    assert patch_title_zero.total_hosts == 0
    assert patch_title_zero.completion_percent == 0.0


@patch("pandas.read_excel")
def test_initialize_dataframe(mock_read_excel, tmp_path, mock_data_manager):
    """Test DataFrame initialization from an Excel file."""
    # Mock the return value of read_excel
    mock_read_excel.return_value = mock_df

    # Create a valid temporary Excel file
    test_excel_path = tmp_path / "test.xlsx"
    mock_df.to_excel(test_excel_path, index=False)

    # Initialize Analyzer
    analyzer = Analyzer(excel_path=test_excel_path, data_manager=mock_data_manager)

    # Assert DataFrame loaded correctly
    assert not analyzer.df.empty
    assert len(analyzer.df) == len(mock_df)


def test_validate_path_success(mock_analyzer, tmp_path):
    """Test file path validation with a valid file."""
    valid_file = tmp_path / "valid_file.xlsx"
    valid_file.touch()
    assert mock_analyzer._validate_path(valid_file)


def test_validate_path_invalid_file(mock_analyzer):
    """Test file path validation with an invalid file."""
    invalid_file = "non_existent.xlsx"
    assert not mock_analyzer._validate_path(invalid_file)


def test_filter_titles(mock_analyzer, mock_data_manager):
    """Test filtering PatchTitle objects by criteria."""
    patch_titles = [
        PatchTitle(
            title="Patch A",
            title_id="0",
            released="2022-01-01",
            hosts_patched=50,
            missing_patch=10,
            latest_version="1.0.0",
            completion_percent=(50 / (50 + 10)) * 100,
            total_hosts=50 + 10,
        ),
        PatchTitle(
            title="Patch B",
            title_id="1",
            released="2023-01-01",
            hosts_patched=30,
            missing_patch=20,
            latest_version="2.0.0",
            completion_percent=(30 / (30 + 20)) * 100,
            total_hosts=30 + 20,
        ),
        PatchTitle(
            title="Patch C",
            title_id="2",
            released="2023-12-01",
            hosts_patched=20,
            missing_patch=5,
            latest_version="3.0.0",
            completion_percent=(20 / (20 + 5)) * 100,
            total_hosts=20 + 5,
        ),
    ]
    mock_data_manager.titles = patch_titles

    # Test MOST_INSTALLED filter
    filtered = mock_analyzer.filter_titles(FilterCriteria.MOST_INSTALLED)
    assert filtered[0].title == "Patch A"

    # Test LEAST_INSTALLED filter
    filtered = mock_analyzer.filter_titles(FilterCriteria.LEAST_INSTALLED)
    assert filtered[0].title == "Patch C"

    # Test BELOW_THRESHOLD filter
    filtered = mock_analyzer.filter_titles(FilterCriteria.BELOW_THRESHOLD, threshold=70.0)
    assert len(filtered) == 1
    assert filtered[0].title == "Patch B"

    # Test ZERO_COMPLETION filter
    patch_titles[0].completion_percent = 0  # Manually set completion percent to zero
    filtered = mock_analyzer.filter_titles(FilterCriteria.ZERO_COMPLETION)
    assert len(filtered) == 1
    assert filtered[0].title == "Patch A"


@pytest.mark.parametrize(
    "criteria, expected_count",
    [
        (FilterCriteria.MOST_INSTALLED, 3),
        (FilterCriteria.LEAST_INSTALLED, 3),
        (FilterCriteria.ZERO_COMPLETION, 0),  # No titles with zero completion initially
    ],
)
def test_filter_titles_parametrized(mock_analyzer, criteria, expected_count, mock_data_manager):
    """Test filtering with parametrized criteria."""
    mock_data_manager.titles = [
        PatchTitle(
            title="Patch A",
            title_id="0",
            released="2022-01-01",
            hosts_patched=50,
            missing_patch=10,
            latest_version="1.0.0",
        ),
        PatchTitle(
            title="Patch B",
            title_id="1",
            released="2023-01-01",
            hosts_patched=30,
            missing_patch=20,
            latest_version="2.0.0",
        ),
        PatchTitle(
            title="Patch C",
            title_id="2",
            released="2023-12-01",
            hosts_patched=20,
            missing_patch=5,
            latest_version="3.0.0",
        ),
    ]
    filtered = mock_analyzer.filter_titles(criteria)
    assert len(filtered) == expected_count
