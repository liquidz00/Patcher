from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.utils.exceptions import PatcherError


# Test successful report processing
@pytest.mark.asyncio
async def test_process_reports_success(
    stop_event_fixture, patcher_instance, mock_policy_response, mock_summary_response
):
    with patch.object(patcher_instance.data_manager, "export") as mock_export_to_excel:
        await patcher_instance.process_reports(
            path="~/",
            formats={"excel", "html"},
            sort=None,
            omit=False,
            ios=False,
            report_title="Test Report",
        )

        assert mock_export_to_excel.called


# Test process reports with invalid path
@pytest.mark.asyncio
@patch("os.makedirs", new_callable=AsyncMock, side_effect=OSError("Read-only file system"))
@patch("os.path.isfile")
async def test_process_reports_invalid_path(
    mock_isfile,
    stop_event_fixture,
    patcher_instance,
    mock_policy_response,
    mock_summary_response,
):
    mock_isfile.return_value = True
    with patch.object(patcher_instance.data_manager, "export") as mock_error:
        await patcher_instance.process_reports(
            path="/invalid/path",
            formats={"excel", "html"},
            sort=None,
            omit=False,
            ios=False,
            report_title="Test Report",
        )

        mock_error.assert_called_once()


# Test invalid sort
@pytest.mark.asyncio
async def test_invalid_sort(
    stop_event_fixture,
    patcher_instance,
):
    with pytest.raises(PatcherError):
        with patch.object(patcher_instance.data_manager, "export") as mock_error:
            await patcher_instance.process_reports(
                path="~/",
                formats={"excel", "html"},
                sort="sort_column",
                omit=False,
                ios=False,
                report_title="Test Report",
            )

            mock_error.assert_called_once()
