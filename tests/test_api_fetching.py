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
