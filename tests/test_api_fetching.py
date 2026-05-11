from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.utils import exceptions


# Test getting policies (success, error)
@pytest.mark.asyncio
async def test_get_policies(api_client, mock_policy_response):
    with patch.object(api_client, "fetch_json", AsyncMock(return_value=mock_policy_response)):
        policies = await api_client.get_policies()

        assert len(policies) == len(mock_policy_response)
        assert policies[0] == mock_policy_response[0]["id"]


@pytest.mark.asyncio
async def test_get_policies_invalid_response(api_client):
    """If fetch_json fails to parse the upstream response, get_policies re-raises."""
    err = exceptions.APIResponseError(
        "Failed parsing JSON response from API",
        url="https://example.com",
        error_msg="Expecting value",
    )
    with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
        with pytest.raises(exceptions.APIResponseError) as excinfo:
            await api_client.get_policies()

        assert "Failed parsing JSON response from API" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_policies_error(api_client):
    """A 4xx response surfaced as APIResponseError propagates through get_policies."""
    err = exceptions.APIResponseError(
        "Client error received.", status_code=401, error="Unauthorized"
    )
    with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
        with pytest.raises(exceptions.APIResponseError):
            await api_client.get_policies()


# Test getting summaries (success, error)
@pytest.mark.asyncio
async def test_get_summaries(api_client, mock_summary_response):
    with patch.object(api_client, "fetch_json", side_effect=mock_summary_response):
        summaries = await api_client.get_summaries(["3", "4", "5"])

        assert summaries[0].title == "Google Chrome"
        assert summaries[1].hosts_patched == 185
        assert summaries[2].completion_percent == 54.55


@pytest.mark.asyncio
async def test_get_summaries_error(api_client):
    """A non-success status from fetch_json surfaces as APIResponseError."""
    err = exceptions.APIResponseError("Unexpected HTTP status code received.", status_code=405)
    with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
        with pytest.raises(exceptions.APIResponseError):
            await api_client.get_summaries(["1", "2", "3"])


# Test SOFA feed (success, error) — post-httpx-migration
@pytest.mark.asyncio
async def test_get_sofa_feed_success(api_client, mock_sofa_response):
    """get_sofa_feed delegates to fetch_json and reshapes the OSVersions field."""
    with patch.object(api_client, "fetch_json", AsyncMock(return_value=mock_sofa_response)):
        versions = await api_client.get_sofa_feed()

    assert len(versions) == 2
    assert versions[0]["OSVersion"] == "17"
    assert versions[0]["ProductVersion"] == "17.5.1"


@pytest.mark.asyncio
async def test_get_sofa_feed_error(api_client):
    """An httpx-layer failure surfaces wrapped as 'Unable to retrieve SOFA feed'."""
    err = exceptions.APIResponseError("Network error fetching URL", url="https://sofafeed")
    with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
        with pytest.raises(exceptions.APIResponseError, match="Unable to retrieve SOFA feed"):
            await api_client.get_sofa_feed()


# Test CSV export (success, error) — post-httpx-migration
@pytest.mark.asyncio
async def test_get_title_report_csv_success(api_client):
    """get_title_report_csv parses the CSV returned by fetch_text into PatchDevice rows."""
    csv_body = (
        "computerName,deviceId,username,operatingSystemVersion,lastContactTime,"
        "buildingName,departmentName,siteName,version\n"
        "Mac1,1,jappleseed,14.5,2024-05-20T00:00:00Z,HQ,Eng,Main,1.0\n"
        "Mac2,2,jappleseed,14.4,2024-05-19T00:00:00Z,HQ,Eng,Main,1.0\n"
    )
    with (
        patch.object(api_client, "_headers", AsyncMock(return_value={"Authorization": "Bearer x"})),
        patch.object(api_client, "fetch_text", AsyncMock(return_value=csv_body)) as mock_fetch,
    ):
        devices = await api_client.get_title_report_csv("123")

    assert len(devices) == 2
    # The `columns-to-export` query param is repeated once per CSV column
    # — confirm fetch_text received the list-of-tuples form.
    call_kwargs = mock_fetch.call_args.kwargs
    assert isinstance(call_kwargs["params"], list)
    assert ("columns-to-export", "computerName") in call_kwargs["params"]
    assert call_kwargs["headers"]["accept"] == "text/csv"


@pytest.mark.asyncio
async def test_get_title_report_csv_error(api_client):
    """A non-success from fetch_text is wrapped into 'Failed to export patch report'."""
    err = exceptions.APIResponseError("Client error received.", status_code=401)
    with (
        patch.object(api_client, "_headers", AsyncMock(return_value={"Authorization": "Bearer x"})),
        patch.object(api_client, "fetch_text", AsyncMock(side_effect=err)),
    ):
        with pytest.raises(exceptions.APIResponseError, match="Failed to export patch report"):
            await api_client.get_title_report_csv("123")
