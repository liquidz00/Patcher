from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.patcher.clients.jamf import JamfClient, JamfSetupClient
from src.patcher.core import exceptions


# Test the from_credentials factory (library entry point)
class TestFromCredentials:
    def test_from_credentials_constructs_apiclient_without_keyring(self):
        """
        JamfClient.from_credentials wires up an in-memory ConfigManager so library
        callers don't need a keyring backend.
        """
        client = JamfClient.from_credentials(
            client_id="cid",
            client_secret="csec",
            server="https://example.com",
        )
        assert isinstance(client, JamfClient)
        assert client.jamf_url == "https://example.com"
        assert client.config.in_memory_mode is True
        assert client.max_concurrency == 5  # default

    def test_from_credentials_honors_concurrency(self):
        client = JamfClient.from_credentials(
            client_id="cid",
            client_secret="csec",
            server="https://example.com",
            concurrency=3,
        )
        assert client.max_concurrency == 3


# Test getting policies (success, error)
class TestGetPolicies:
    @pytest.mark.asyncio
    async def test_get_policies(self, api_client, mock_policy_response):
        with patch.object(api_client, "fetch_json", AsyncMock(return_value=mock_policy_response)):
            policies = await api_client.get_policies()

            assert len(policies) == len(mock_policy_response)
            assert policies[0] == mock_policy_response[0]["id"]

    @pytest.mark.asyncio
    async def test_get_policies_invalid_response(self, api_client):
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
    async def test_get_policies_error(self, api_client):
        """A 4xx response surfaced as APIResponseError propagates through get_policies."""
        err = exceptions.APIResponseError(
            "Client error received.", status_code=401, error="Unauthorized"
        )
        with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
            with pytest.raises(exceptions.APIResponseError):
                await api_client.get_policies()


# Test getting summaries (success, error)
class TestGetSummaries:
    @pytest.mark.asyncio
    async def test_get_summaries(self, api_client, mock_summary_response):
        with patch.object(api_client, "fetch_json", side_effect=mock_summary_response):
            summaries = await api_client.get_summaries(["3", "4", "5"])

            assert summaries[0].title == "Google Chrome"
            assert summaries[1].hosts_patched == 185
            assert summaries[2].completion_percent == 54.55

    @pytest.mark.asyncio
    async def test_get_summaries_error(self, api_client):
        """A non-success status from fetch_json surfaces as APIResponseError."""
        err = exceptions.APIResponseError("Unexpected HTTP status code received.", status_code=405)
        with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
            with pytest.raises(exceptions.APIResponseError):
                await api_client.get_summaries(["1", "2", "3"])


# Test SOFA feed (success, error) — post-httpx-migration
class TestGetSofaFeed:
    @pytest.mark.asyncio
    async def test_get_sofa_feed_success(self, api_client, mock_sofa_response):
        """get_sofa_feed delegates to fetch_json and reshapes the OSVersions field."""
        with patch.object(api_client, "fetch_json", AsyncMock(return_value=mock_sofa_response)):
            versions = await api_client.get_sofa_feed()

        assert len(versions) == 2
        assert versions[0]["OSVersion"] == "17"
        assert versions[0]["ProductVersion"] == "17.5.1"

    @pytest.mark.asyncio
    async def test_get_sofa_feed_error(self, api_client):
        """An httpx-layer failure surfaces wrapped as 'Unable to retrieve SOFA feed'."""
        err = exceptions.APIResponseError("Network error fetching URL", url="https://sofafeed")
        with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
            with pytest.raises(exceptions.APIResponseError, match="Unable to retrieve SOFA feed"):
                await api_client.get_sofa_feed()


# Test CSV export (success, error) — post-httpx-migration
class TestGetTitleReportCsv:
    @pytest.mark.asyncio
    async def test_get_title_report_csv_success(self, api_client):
        """get_title_report_csv parses the CSV returned by fetch_text into PatchDevice rows."""
        csv_body = (
            "computerName,deviceId,username,operatingSystemVersion,lastContactTime,"
            "buildingName,departmentName,siteName,version\n"
            "Mac1,1,jappleseed,14.5,2024-05-20T00:00:00Z,HQ,Eng,Main,1.0\n"
            "Mac2,2,jappleseed,14.4,2024-05-19T00:00:00Z,HQ,Eng,Main,1.0\n"
        )
        with (
            patch.object(
                api_client, "_headers", AsyncMock(return_value={"Authorization": "Bearer x"})
            ),
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
    async def test_get_title_report_csv_error(self, api_client):
        """A non-success from fetch_text is wrapped into 'Failed to export patch report'."""
        err = exceptions.APIResponseError("Client error received.", status_code=401)
        with (
            patch.object(
                api_client, "_headers", AsyncMock(return_value={"Authorization": "Bearer x"})
            ),
            patch.object(api_client, "fetch_text", AsyncMock(side_effect=err)),
        ):
            with pytest.raises(exceptions.APIResponseError, match="Failed to export patch report"):
                await api_client.get_title_report_csv("123")


class TestGetTitleReports:
    @pytest.mark.asyncio
    async def test_get_title_reports_maps_titles_and_isolates_failures(self, api_client):
        """Each title maps to its device list; a per-title APIResponseError degrades to []."""

        async def fake_csv(title_id):
            if title_id == "bad":
                raise exceptions.APIResponseError("boom", status_code=500)
            return [f"device-for-{title_id}"]

        api_client.get_title_report_csv = AsyncMock(side_effect=fake_csv)

        result = await api_client.get_title_reports(["good", "bad", "good2"])

        assert result["good"] == ["device-for-good"]
        assert result["good2"] == ["device-for-good2"]
        assert result["bad"] == []  # failure isolated, not propagated


class TestJamfSetupClient:
    """The credential-free first-run provisioning client (basic token + API role/client)."""

    @pytest.mark.asyncio
    async def test_fetch_basic_token(self):
        """fetch_basic_token POSTs with Basic auth and extracts the token from the response."""
        client = JamfSetupClient(jamf_url="https://example.com")
        mock_response = Mock(status_code=200, is_success=True)
        mock_response.json.return_value = {"token": "abc123"}
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http

        result = await client.fetch_basic_token("user", "pass")

        assert result == "abc123"
        # Basic auth via httpx's auth= kwarg (not in URL/body), against the instance URL.
        assert mock_http.post.call_args.kwargs["auth"] == ("user", "pass")
        assert mock_http.post.call_args.args[0].startswith("https://example.com")

    @pytest.mark.asyncio
    async def test_create_roles(self):
        """create_roles orchestrates a single fetch_json POST; mock at that layer."""
        client = JamfSetupClient(jamf_url="https://example.com")
        with patch.object(
            client, "fetch_json", AsyncMock(return_value={"displayName": "Patcher-Role"})
        ) as mock_fetch:
            assert await client.create_roles("token") is True
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_client(self):
        """create_client makes two fetch_json calls — one for the integration, one for the secret."""
        client = JamfSetupClient(jamf_url="https://example.com")
        with patch.object(
            client,
            "fetch_json",
            AsyncMock(side_effect=[{"clientId": "123", "id": "456"}, {"clientSecret": "secret"}]),
        ) as mock_fetch:
            assert await client.create_client("token") == ("123", "secret")
            assert mock_fetch.call_count == 2
