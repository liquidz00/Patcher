import pytest
from aioresponses import aioresponses


@pytest.mark.asyncio
async def test_get_policies(
    api_client, mock_policy_response, mock_api_integration_response
):
    base_url = api_client.jamf_url
    api_client.jamf_client.client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{base_url}/api/v2/patch-software-title-configurations",
            payload=mock_policy_response,
            headers={"Accept": "application/json"},
        )
        m.get(
            f"{base_url}/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )

        policies = await api_client.get_policies()
        assert len(policies) == len(mock_policy_response)
        assert policies[0] == mock_policy_response[0]["id"]


@pytest.mark.asyncio
async def test_get_summaries(
    api_client,
    mock_policy_response,
    mock_summary_response,
    mock_api_integration_response,
):
    base_url = api_client.jamf_url
    api_client.jamf_client.client_id = "a1234567-abcd-1234-efgh-123456789abc"
    policy_ids = [policy["id"] for policy in mock_policy_response]
    summary_response_dict = {
        str(summary["softwareTitleId"]): summary for summary in mock_summary_response
    }
    with aioresponses() as m:
        for policy_id in policy_ids:
            mock_response = summary_response_dict[policy_id]
            m.get(
                f"{base_url}/api/v2/patch-software-title-configurations/{policy_id}/patch-summary",
                payload=mock_response,
                headers={"Accept": "application/json"},
            )
            m.get(
                f"{base_url}/api/v1/api-integrations",
                payload=mock_api_integration_response,
                headers={"Accept": "application/json"},
            )

        summaries = await api_client.get_summaries(policy_ids)
        assert summaries[0]["software_title"] == "Google Chrome"
        assert summaries[1]["hosts_patched"] == 185
        assert summaries[2]["completion_percent"] == 54.55


@pytest.mark.asyncio
async def test_get_policies_empty_response(api_client, mock_api_integration_response):
    base_url = api_client.jamf_url
    api_client.jamf_client.client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{base_url}/api/v2/patch-software-title-configurations",
            payload=[],
            headers={"Accept": "application/json"},
        )
        m.get(
            f"{base_url}/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )

        policies = await api_client.get_policies()
        assert policies == []


@pytest.mark.asyncio
async def test_get_policies_api_error(api_client, mock_api_integration_response):
    base_url = api_client.jamf_url
    api_client.jamf_client.client_id = "a1234567-abcd-1234-efgh-123456789abc"
    with aioresponses() as m:
        m.get(
            f"{base_url}/api/v2/patch-software-title-configurations",
            status=500,
            headers={"Accept": "application/json"},
        )
        m.get(
            f"{base_url}/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )

        policies = await api_client.get_policies()
        assert policies is None
