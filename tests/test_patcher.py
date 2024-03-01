import aiohttp
import pytest
import os
import aioresponses
from patcher import get_policies, get_summaries, main_async, convert_timezone
from tempfile import TemporaryDirectory
from dotenv import load_dotenv
from click.testing import CliRunner

BASE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.dirname(BASE)
ENV_PATH = os.path.join(ROOT, ".env")

load_dotenv(dotenv_path=ENV_PATH)
jamf_url = os.getenv("URL")
jamf_client_id = os.getenv("CLIENT_ID")
jamf_client_secret = os.getenv("CLIENT_SECRET")
jamf_token = os.getenv("TOKEN")

# Headers for API calls
headers = {"Accept": "application/json", "Authorization": f"Bearer {jamf_token}"}


@pytest.fixture()
def mock_policy_response():
    """Fixture to provide a mock policy response."""
    yield [
        {
            "id": "3",
            "jamfOfficial": True,
            "displayName": "Google Chrome",
            "categoryId": "3",
            "siteId": "-1",
            "uiNotifications": True,
            "emailNotifications": False,
            "softwareTitleId": "3",
            "extensionAttributes": [],
            "softwareTitleName": "Google Chrome",
            "softwareTitleNameId": "0BC",
            "softwareTitlePublisher": "Google",
            "patchSourceName": "Jamf",
            "patchSourceEnabled": True,
            "packages": [],
        },
        {
            "id": "4",
            "jamfOfficial": True,
            "displayName": "Jamf Connect",
            "categoryId": "19",
            "siteId": "-1",
            "uiNotifications": True,
            "emailNotifications": False,
            "softwareTitleId": "4",
            "extensionAttributes": [],
            "softwareTitleName": "Jamf Connect",
            "softwareTitleNameId": "JamfConnect",
            "softwareTitlePublisher": "Jamf",
            "patchSourceName": "Jamf",
            "patchSourceEnabled": True,
            "packages": [],
        },
        {
            "id": "5",
            "jamfOfficial": True,
            "displayName": "Apple macOS Ventura",
            "categoryId": "8",
            "siteId": "-1",
            "uiNotifications": True,
            "emailNotifications": True,
            "softwareTitleId": "5",
            "extensionAttributes": [],
            "softwareTitleName": "Apple macOS Ventura",
            "softwareTitleNameId": "53E",
            "softwareTitlePublisher": "Apple",
            "patchSourceName": "Jamf",
            "patchSourceEnabled": True,
            "packages": [],
        },
    ]


@pytest.fixture()
def mock_summary_response():
    """Fixture to provide mock summary responses for each policy."""
    yield [
        {
            "softwareTitleId": "3",
            "softwareTitleConfigurationId": "3",
            "title": "Google Chrome",
            "latestVersion": "122.0.6261.57",
            "releaseDate": "2024-02-21T09:43:36Z",
            "upToDate": 23,
            "outOfDate": 163,
            "onDashboard": True,
        },
        {
            "softwareTitleId": "4",
            "softwareTitleConfigurationId": "4",
            "title": "Jamf Connect",
            "latestVersion": "2.32.0",
            "releaseDate": "2024-02-05T20:07:10Z",
            "upToDate": 185,
            "outOfDate": 19,
            "onDashboard": True,
        },
        {
            "softwareTitleId": "5",
            "softwareTitleConfigurationId": "5",
            "title": "Apple macOS Ventura",
            "latestVersion": "13.6.4 (22G513)",
            "releaseDate": "2024-01-23T01:13:19Z",
            "upToDate": 6,
            "outOfDate": 5,
            "onDashboard": True,
        },
    ]


@pytest.mark.asyncio
async def test_get_policies(mock_policy_response):
    with aioresponses.aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            payload=mock_policy_response,
            headers=headers,
        )

        async with aiohttp.ClientSession() as session:
            policies = await get_policies()
            assert len(policies) == len(mock_policy_response)
            assert policies[0] == mock_policy_response[0]["id"]


@pytest.mark.asyncio
async def test_get_summaries(mock_policy_response, mock_summary_response):
    policy_ids = [policy["id"] for policy in mock_policy_response]
    summary_response_dict = {
        str(summary["softwareTitleId"]): summary for summary in mock_summary_response
    }
    with aioresponses.aioresponses() as m:
        for policy_id in policy_ids:
            mock_response = summary_response_dict[policy_id]
            m.get(
                f"{jamf_url}/api/v2/patch-software-title-configurations/{policy_id}/patch-summary",
                payload=mock_response,
                headers=headers,
            )

        summaries = await get_summaries(policy_ids)
        assert summaries[0]["software_title"] == "Google Chrome"
        assert summaries[1]["hosts_patched"] == 185
        assert summaries[2]["completion_percent"] == 54.55


@pytest.mark.asyncio
async def test_get_policies_empty_response():
    with aioresponses.aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            payload=[],
            headers=headers,
        )

        async with aiohttp.ClientSession() as session:
            policies = await get_policies()
            assert policies == []


@pytest.mark.asyncio
async def test_get_policies_api_error():
    with aioresponses.aioresponses() as m:
        m.get(
            f"{jamf_url}/api/v2/patch-software-title-configurations",
            status=500,
            headers=headers,
        )

        async with aiohttp.ClientSession() as session:
            with pytest.raises(Exception):
                await get_policies()


@pytest.mark.asyncio
async def test_get_summaries_empty_ids():
    summaries = await get_summaries([])
    assert summaries == []


@pytest.mark.asyncio
async def test_get_summaries_api_error(mock_policy_response):
    policy_ids = [policy["id"] for policy in mock_policy_response]
    with aioresponses.aioresponses() as m:
        for policy_id in policy_ids:
            m.get(
                f"{jamf_url}/api/v2/patch-software-title-configurations/{policy_id}/patch-summary",
                status=500,
                headers=headers,
            )

        with pytest.raises(Exception):
            await get_summaries(policy_ids)


@pytest.mark.asyncio
async def test_summary_response_data_integrity(mock_summary_response):
    for summary in mock_summary_response:
        assert "softwareTitleId" in summary
        assert "upToDate" in summary and "outOfDate" in summary


def test_main_async_default_options():
    with TemporaryDirectory() as temp_dir:
        runner = CliRunner()
        result = runner.invoke(main_async, ["--path", temp_dir])
        assert result.exit_code == 0


def test_convert_timezone_invalid():
    with pytest.raises(ValueError):
        convert_timezone("invalid-time-format")
