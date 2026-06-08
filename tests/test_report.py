from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.cli._helpers import process_reports
from src.patcher.core.exceptions import APIResponseError, PatcherError


# Test successful report processing
@pytest.mark.asyncio
async def test_process_reports_success(
    stop_event_fixture, patcher_instance, mock_policy_response, mock_summary_response
):
    with patch.object(patcher_instance, "export") as mock_export_to_excel:
        await process_reports(
            patcher_instance,
            path="~/",
            formats={"excel", "html"},
            sort=None,
            omit=False,
            ios=False,
            report_title="Test Report",
            header_color="",
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
    with patch.object(patcher_instance, "export") as mock_error:
        await process_reports(
            patcher_instance,
            path="/invalid/path",
            formats={"excel", "html"},
            sort=None,
            omit=False,
            ios=False,
            report_title="Test Report",
            header_color="",
        )

        mock_error.assert_called_once()


# Test invalid sort
@pytest.mark.asyncio
async def test_invalid_sort(
    stop_event_fixture,
    patcher_instance,
):
    with pytest.raises(PatcherError):
        with patch.object(patcher_instance, "export") as mock_error:
            await process_reports(
                patcher_instance,
                path="~/",
                formats={"excel", "html"},
                sort="sort_column",
                omit=False,
                ios=False,
                report_title="Test Report",
                header_color="",
            )

            mock_error.assert_called_once()


@pytest.mark.asyncio
async def test_process_reports_all_optional_steps(patcher_instance, mocker):
    """sort + omit + ios + device-details + matching all run through to export."""
    mocker.patch(
        "src.patcher.cli._helpers.sort_titles", new_callable=AsyncMock, side_effect=lambda r, s: r
    )
    mocker.patch(
        "src.patcher.cli._helpers.omit_recent", new_callable=AsyncMock, side_effect=lambda r: r
    )
    mocker.patch(
        "src.patcher.cli._helpers.append_ios_status",
        new_callable=AsyncMock,
        side_effect=lambda r, j: r,
    )
    mocker.patch("src.patcher.cli._helpers.match_titles", new_callable=AsyncMock)
    patcher_instance.jamf.get_title_reports = AsyncMock(return_value={"1": []})

    await process_reports(
        patcher_instance,
        path="~/",
        formats={"excel"},
        sort="released",
        omit=True,
        ios=True,
        report_title="T",
        header_color="",
        device_details=True,
    )

    assert patcher_instance.export.called
    patcher_instance.jamf.get_title_reports.assert_called_once()


@pytest.mark.asyncio
async def test_process_reports_policy_fetch_error(patcher_instance):
    patcher_instance.jamf.get_policies = AsyncMock(
        side_effect=APIResponseError("down", status_code=503)
    )
    with pytest.raises(PatcherError, match="policy IDs"):
        await process_reports(
            patcher_instance,
            path="~/",
            formats={"excel"},
            sort=None,
            omit=False,
            ios=False,
            report_title="T",
            header_color="",
        )


@pytest.mark.asyncio
async def test_process_reports_summary_fetch_error(patcher_instance):
    patcher_instance.jamf.get_summaries = AsyncMock(
        side_effect=APIResponseError("down", status_code=503)
    )
    with pytest.raises(PatcherError, match="patch summaries"):
        await process_reports(
            patcher_instance,
            path="~/",
            formats={"excel"},
            sort=None,
            omit=False,
            ios=False,
            report_title="T",
            header_color="",
        )


@pytest.mark.asyncio
async def test_process_reports_matching_error_reraises(patcher_instance, mocker):
    mocker.patch(
        "src.patcher.cli._helpers.match_titles",
        new_callable=AsyncMock,
        side_effect=APIResponseError("boom", status_code=500),
    )
    with pytest.raises(APIResponseError):
        await process_reports(
            patcher_instance,
            path="~/",
            formats={"excel"},
            sort=None,
            omit=False,
            ios=False,
            report_title="T",
            header_color="",
        )


@pytest.mark.asyncio
async def test_process_reports_matching_404_is_swallowed(patcher_instance, mocker):
    mocker.patch(
        "src.patcher.cli._helpers.match_titles",
        new_callable=AsyncMock,
        side_effect=APIResponseError("not found", status_code=404, not_found=True),
    )
    await process_reports(
        patcher_instance,
        path="~/",
        formats={"excel"},
        sort=None,
        omit=False,
        ios=False,
        report_title="T",
        header_color="",
    )
    assert patcher_instance.export.called  # 404 swallowed, run continues
