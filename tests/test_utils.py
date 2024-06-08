import pytest
import aioresponses
from bin import utils
from conftest import jamf_url, headers


def test_convert_timezone_invalid():
    result = utils.convert_timezone("invalid time format")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_token_api_failure(mock_env_vars):
    with aioresponses.aioresponses() as m:
        m.post(f"{jamf_url}/api/oauth/token", status=500)
        token = await utils.fetch_token()
        assert token is None


@pytest.mark.asyncio
async def test_get_summaries_empty_ids(mock_env_vars):
    summaries = await utils.get_summaries([])
    assert summaries == []


@pytest.mark.asyncio
async def test_get_summaries_api_error(mock_policy_response, mock_summary_response, mock_env_vars):
    policy_ids = [policy["id"] for policy in mock_policy_response]
    with aioresponses.aioresponses() as m:
        for policy_id in policy_ids:
            m.get(
                f"{jamf_url}/api/v2/patch-software-title-configurations/{policy_id}/patch-summary",
                status=500,
                payload=mock_policy_response,
                headers=headers,
            )

        summaries = await utils.get_summaries(policy_ids)
        assert summaries == []


@pytest.mark.asyncio
async def test_summary_response_data_integrity(mock_summary_response):
    for summary in mock_summary_response:
        assert "softwareTitleId" in summary
        assert "upToDate" in summary and "outOfDate" in summary
