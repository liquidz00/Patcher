import pytest
import threading
import click.testing

from unittest.mock import patch, AsyncMock, MagicMock

from patcher import process_reports
from src import logger

@pytest.fixture
def mock_setup_child_logger():
    with patch('src.logger.setup_child_logger') as mock:
        mock_logger = MagicMock()
        mock.return_value = mock_logger
        yield mock


@pytest.fixture(scope="function", autouse=True)
def stop_event_fixture():
    stop_event = threading.Event()
    yield stop_event
    stop_event.set()


# Test logging functionality - Info
def test_log_me_info(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = logger.LogMe(mock_logger)
    log_me.info("This is an info message")
    mock_logger.info.assert_called_once_with("This is an info message")

    captured = capsys.readouterr()
    assert 'This is an info message' in captured.out


# Test logging functionality - Error
def test_log_me_error(mock_setup_child_logger, capsys):
    mock_logger = mock_setup_child_logger.return_value
    log_me = logger.LogMe(mock_logger)
    log_me.error("This is an error message")
    mock_logger.error.assert_called_once_with("This is an error message")

    captured = capsys.readouterr()
    assert 'This is an error message' in captured.err


# Test successful report processing
@pytest.mark.asyncio
@patch("src.utils.token_valid", return_value=True)
@patch("src.utils.check_token_lifetime", return_value=True)
@patch(
    "src.utils.get_policies",
    return_value=AsyncMock(return_value=["policy1", "policy2"]),
)
@patch(
    "src.utils.get_summaries",
    return_value=AsyncMock(return_value=[{"patch_released": "2024-05-20"}]),
)
@patch("src.utils.export_to_excel")
async def test_process_reports_success(
    mock_export_to_excel,
    mock_get_summaries,
    mock_get_policies,
    mock_check_token_lifetime,
    mock_token_valid,
    stop_event_fixture,
):
    await process_reports(
        path="~/",
        pdf=False,
        sort=None,
        omit=False,
        ios=False,
        stop_event=stop_event_fixture,
    )
    assert mock_export_to_excel.called


# Test process reports with invalid path
@pytest.mark.asyncio
@patch("os.makedirs", MagicMock(side_effect=OSError("Read-only file system")))
@patch("os.path.isfile", return_value=True)
async def test_process_reports_invalid_path(mock_isfile, stop_event_fixture):
    with patch("src.logger.logthis.error") as mock_error, pytest.raises(click.Abort):
        await process_reports(
            path="/invalid/path",
            pdf=False,
            sort=None,
            omit=False,
            ios=False,
            stop_event=stop_event_fixture,
        )
        mock_error.assert_called_once()


# Test token validation and refresh
@pytest.mark.asyncio
@patch("src.utils.token_valid", return_value=False)
@patch("src.utils.fetch_token", new_callable=AsyncMock, return_value=None)
async def test_process_reports_token_refresh_fail(
    mock_fetch_token, mock_token_valid, stop_event_fixture
):
    with patch("src.logger.logthis.error") as mock_error, pytest.raises(click.Abort):
        await process_reports(
            path="~/",
            pdf=False,
            sort=None,
            omit=False,
            ios=False,
            stop_event=stop_event_fixture,
        )
        mock_error.assert_called_once()


# Test sorting and omission options
@pytest.mark.asyncio
@patch("src.utils.token_valid", return_value=True)
@patch("src.utils.check_token_lifetime", return_value=True)
@patch(
    "src.utils.get_policies",
    return_value=AsyncMock(return_value=["policy1", "policy2"]),
)
@patch(
    "src.utils.get_summaries",
    return_value=AsyncMock(
        return_value=[
            {"patch_released": "2024-05-20", "sort_column": "B"},
            {"patch_released": "2024-05-18", "sort_column": "A"},
        ]
    ),
)
@patch("src.utils.export_to_excel")
async def test_process_reports_sorting(
    mock_export_to_excel,
    mock_get_summaries,
    mock_get_policies,
    mock_check_token_lifetime,
    mock_token_valid,
    stop_event_fixture,
):
    await process_reports(
        path="~/",
        pdf=False,
        sort="sort_column",
        omit=False,
        ios=False,
        stop_event=stop_event_fixture,
    )
    assert mock_export_to_excel.called


# Test omission
@pytest.mark.asyncio
@patch("src.utils.token_valid", return_value=True)
@patch("src.utils.check_token_lifetime", return_value=True)
@patch(
    "src.utils.get_policies",
    return_value=AsyncMock(return_value=["policy1", "policy2"]),
)
@patch(
    "src.utils.get_summaries",
    return_value=AsyncMock(
        return_value=[
            {"patch_released": "2024-05-20"},
            {"patch_released": "2024-05-18"},
        ]
    ),
)
@patch("src.utils.export_to_excel")
async def test_process_reports_omit(
    mock_export_to_excel,
    mock_get_summaries,
    mock_get_policies,
    mock_check_token_lifetime,
    mock_token_valid,
    stop_event_fixture,
):
    await process_reports(
        path="~/",
        pdf=False,
        sort=None,
        omit=True,
        ios=False,
        stop_event=stop_event_fixture,
    )
    assert mock_export_to_excel.called


# Test iOS inclusion
@pytest.mark.asyncio
@patch("src.utils.token_valid", return_value=True)
@patch("src.utils.check_token_lifetime", return_value=True)
@patch(
    "src.utils.get_policies",
    new_callable=AsyncMock,
    return_value=["policy1", "policy2"],
)
@patch(
    "src.utils.get_summaries",
    new_callable=AsyncMock,
    return_value=[{"patch_released": "2024-05-20"}],
)
@patch(
    "src.utils.get_device_ids",
    new_callable=AsyncMock,
    return_value=["device1", "device2"],
)
@patch(
    "src.utils.get_device_os_versions",
    new_callable=AsyncMock,
    return_value=[{"OS": "17.5.1"}, {"OS": "16.7.8"}],
)
@patch(
    "src.utils.get_sofa_feed",
    return_value=[
        {"OSVersion": "17", "ProductVersion": "17.5.1"},
        {"OSVersion": "16", "ProductVersion": "16.7.8"},
    ],
)
@patch("src.utils.calculate_ios_on_latest")
@patch("src.utils.export_to_excel")
async def test_process_reports_ios(
    mock_export_to_excel,
    mock_calculate_ios_on_latest,
    mock_get_sofa_feed,
    mock_get_device_os_versions,
    mock_get_device_ids,
    mock_get_summaries,
    mock_get_policies,
    mock_check_token_lifetime,
    mock_token_valid,
    stop_event_fixture,
):
    mock_calculate_ios_on_latest.return_value = [{"iOSData": "Data"}]
    await process_reports(
        path="~/",
        pdf=False,
        sort=None,
        omit=False,
        ios=True,
        stop_event=stop_event_fixture,
    )
    assert mock_export_to_excel.called
