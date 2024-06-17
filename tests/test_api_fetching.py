import pytest
from aioresponses import aioresponses
from bin import utils
from conftest import jamf_url, headers

@pytest.mark.asyncio
async def test_get_policies(mock_policy_response, mock_env_vars):
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            payload=mock_policy_response,
            headers=headers,
        )

        policies = await utils.get_policies()
        assert len(policies) == len(mock_policy_response)
        assert policies[0] == mock_policy_response[0]["id"]


@pytest.mark.asyncio
async def test_get_summaries(mock_policy_response, mock_summary_response, mock_env_vars):
    policy_ids = [policy["id"] for policy in mock_policy_response]
    summary_response_dict = {
        str(summary["softwareTitleId"]): summary for summary in mock_summary_response
    }
    with aioresponses() as m:
        for policy_id in policy_ids:
            mock_response = summary_response_dict[policy_id]
            m.get(
                f"{jamf_url}/api/v2/patch-software-title-configurations/{policy_id}/patch-summary",
                payload=mock_response,
                headers=headers,
            )

        summaries = await utils.get_summaries(policy_ids)
        assert summaries[0]["software_title"] == "Google Chrome"
        assert summaries[1]["hosts_patched"] == 185
        assert summaries[2]["completion_percent"] == 54.55


@pytest.mark.asyncio
async def test_get_policies_empty_response(mock_env_vars):
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            payload=[],
            headers=headers,
        )

        policies = await utils.get_policies()
        assert policies == []


@pytest.mark.asyncio
async def test_get_policies_api_error(mock_env_vars):
    with aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            status=500,
            headers=headers,
        )

        policies = await utils.get_policies()
        assert policies is None
