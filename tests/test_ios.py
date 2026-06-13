from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.core import exceptions
from src.patcher.core.analyze import append_ios_status, calculate_ios_on_latest
from src.patcher.core.models.patch import PatchTitle


def _patch_title(title: str, title_id: str) -> PatchTitle:
    return PatchTitle(
        title=title,
        title_id=title_id,
        released="2026-01-01",
        hosts_patched=1,
        missing_patch=0,
        latest_version="1.0",
    )


class TestAppendIosStatus:
    @pytest.mark.asyncio
    async def test_append_ios_status_appends_calculated_titles(self, mocker):
        """The happy path fetches IDs → versions → SOFA and extends the title list."""
        api = AsyncMock()
        api.get_device_ids.return_value = [1, 2]
        api.get_device_os_versions.return_value = [{"OS": "17.5", "DeviceID": "1"}]
        sofa = mocker.patch(
            "src.patcher.core.analyze.get_sofa_feed",
            AsyncMock(
                return_value=[
                    {"OSVersion": "iOS 17", "ProductVersion": "17.5", "ReleaseDate": "2026-01-01"}
                ]
            ),
        )
        ios_title = _patch_title("iOS 17", "iOS")
        mocker.patch("src.patcher.core.analyze.calculate_ios_on_latest", return_value=[ios_title])

        result = await append_ios_status([_patch_title("Firefox", "1")], api)

        assert result[-1].title == "iOS 17"
        api.get_device_ids.assert_awaited_once()
        api.get_device_os_versions.assert_awaited_once_with(device_ids=[1, 2])
        sofa.assert_awaited_once_with(api)

    @pytest.mark.parametrize(
        "failing", ["get_device_ids", "get_device_os_versions", "get_sofa_feed"]
    )
    @pytest.mark.asyncio
    async def test_append_ios_status_wraps_api_errors(self, failing, mocker):
        """An APIResponseError from any of the three fetches becomes a PatcherError."""
        api = AsyncMock()
        api.get_device_ids.return_value = [1]
        api.get_device_os_versions.return_value = [{"OS": "17.5", "DeviceID": "1"}]
        err = exceptions.APIResponseError("boom", status_code=500)
        if failing == "get_sofa_feed":
            mocker.patch("src.patcher.core.analyze.get_sofa_feed", AsyncMock(side_effect=err))
        else:
            getattr(api, failing).side_effect = err

        with pytest.raises(exceptions.PatcherError):
            await append_ios_status([], api)


class TestGetDeviceIds:
    # Test valid response - iOS device IDs
    @pytest.mark.asyncio
    async def test_get_device_ids_valid(self, api_client, mock_ios_device_id_list_response):
        with patch.object(
            api_client, "fetch_json", AsyncMock(return_value=mock_ios_device_id_list_response)
        ):
            devices = await api_client.get_device_ids()

            assert devices is not None
            assert len(devices) == len(mock_ios_device_id_list_response["results"])
            assert devices[0] == mock_ios_device_id_list_response.get("results")[0]["id"]

    # Test invalid response - iOS device IDs
    @pytest.mark.asyncio
    async def test_get_device_ids_invalid(self, api_client):
        """If fetch_json fails to parse upstream, get_device_ids re-raises."""
        err = exceptions.APIResponseError(
            "Failed parsing JSON response from API",
            url="https://example.com",
            error_msg="Expecting value",
        )
        with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
            with pytest.raises(exceptions.APIResponseError) as excinfo:
                await api_client.get_device_ids()

            assert "Failed parsing JSON response from API" in str(excinfo.value)

    # Test API error response
    @pytest.mark.asyncio
    async def test_get_device_ids_api_error(self, api_client):
        """A 4xx upstream surfaces as APIResponseError through get_device_ids."""
        err = exceptions.APIResponseError(
            "Client error received.", status_code=401, error="Unauthorized"
        )
        with patch.object(api_client, "fetch_json", AsyncMock(side_effect=err)):
            with pytest.raises(exceptions.APIResponseError):
                await api_client.get_device_ids()

    # Test valid response - Getting iOS Versions
    @pytest.mark.asyncio
    async def test_get_ios_versions_valid(self, api_client, mock_ios_detail_response):
        device_ids = [1]
        with patch.object(
            api_client, "fetch_json", AsyncMock(return_value=mock_ios_detail_response)
        ):
            fetched_devices = await api_client.get_device_os_versions(device_ids)

        assert fetched_devices[0].get("SN") == mock_ios_detail_response.get("serialNumber")
        assert fetched_devices[0].get("OS") == mock_ios_detail_response.get("osVersion")


class TestCalculateIosOnLatest:
    # Test successful calculation
    @pytest.mark.asyncio
    async def test_calculate_ios_on_latest_success(self, patcher_instance):
        device_versions = [
            {"DeviceID": "1", "OS": "17.5.1"},
            {"DeviceID": "2", "OS": "16.7.8"},
            {"DeviceID": "3", "OS": "17.5.1"},
        ]
        latest_versions = [
            {
                "OSVersion": "17",
                "ProductVersion": "17.5.1",
                "ReleaseDate": "2024-05-20T00:00:00Z",
            },
            {
                "OSVersion": "16",
                "ProductVersion": "16.7.8",
                "ReleaseDate": "2024-05-13T00:00:00Z",
            },
        ]
        result = calculate_ios_on_latest(device_versions, latest_versions)
        expected_result = [
            PatchTitle(
                title="iOS 17.5.1",
                title_id="iOS",
                released="2024-05-20T00:00:00Z",
                hosts_patched=2,
                missing_patch=0,
                latest_version="17.5.1",
                completion_percent=100.0,
                total_hosts=2,
            ),
            PatchTitle(
                title="iOS 16.7.8",
                title_id="iOS",
                released="2024-05-13T00:00:00Z",
                hosts_patched=1,
                missing_patch=0,
                latest_version="16.7.8",
                completion_percent=100.0,
                total_hosts=1,
            ),
        ]

        assert result == expected_result

    # Test no devices on the latest version
    @pytest.mark.asyncio
    async def test_calculate_ios_on_latest_no_devices_on_latest(self, patcher_instance):
        device_versions = [
            {"DeviceID": "1", "OS": "17.4.0"},
            {"DeviceID": "2", "OS": "16.6.0"},
        ]
        latest_versions = [
            {
                "OSVersion": "17",
                "ProductVersion": "17.5.1",
                "ReleaseDate": "2024-05-20T00:00:00Z",
            },
            {
                "OSVersion": "16",
                "ProductVersion": "16.7.8",
                "ReleaseDate": "2024-05-13T00:00:00Z",
            },
        ]
        result = calculate_ios_on_latest(device_versions, latest_versions)
        expected_result = [
            PatchTitle(
                title="iOS 17.5.1",
                title_id="iOS",
                released="2024-05-20T00:00:00Z",
                hosts_patched=0,
                missing_patch=1,
                latest_version="17.5.1",
                completion_percent=0.0,
                total_hosts=1,
            ),
            PatchTitle(
                title="iOS 16.7.8",
                title_id="iOS",
                released="2024-05-13T00:00:00Z",
                hosts_patched=0,
                missing_patch=1,
                latest_version="16.7.8",
                completion_percent=0.0,
                total_hosts=1,
            ),
        ]

        assert result == expected_result

    # Test all devices on the latest version
    @pytest.mark.asyncio
    async def test_calculate_ios_on_latest_all_devices_on_latest(self, patcher_instance):
        device_versions = [
            {"DeviceID": "1", "OS": "17.5.1"},
            {"DeviceID": "2", "OS": "17.5.1"},
        ]
        latest_versions = [
            {
                "OSVersion": "17",
                "ProductVersion": "17.5.1",
                "ReleaseDate": "2024-05-20T00:00:00Z",
            },
        ]

        result = calculate_ios_on_latest(device_versions, latest_versions)
        expected_result = [
            PatchTitle(
                title="iOS 17.5.1",
                title_id="iOS",
                released="2024-05-20T00:00:00Z",
                hosts_patched=2,
                missing_patch=0,
                latest_version="17.5.1",
                completion_percent=100.0,
                total_hosts=2,
            ),
        ]

        assert result == expected_result

    # Test some devices on the latest version
    @pytest.mark.asyncio
    async def test_calculate_ios_on_latest_some_devices_on_latest(self, patcher_instance):
        device_versions = [
            {"DeviceID": "1", "OS": "17.5.1"},
            {"DeviceID": "2", "OS": "17.4.0"},
        ]
        latest_versions = [
            {
                "OSVersion": "17",
                "ProductVersion": "17.5.1",
                "ReleaseDate": "2024-05-20T00:00:00Z",
            },
        ]

        result = calculate_ios_on_latest(device_versions, latest_versions)
        expected_result = [
            PatchTitle(
                title="iOS 17.5.1",
                title_id="iOS",
                released="2024-05-20T00:00:00Z",
                hosts_patched=1,
                missing_patch=1,
                latest_version="17.5.1",
                completion_percent=50.0,
                total_hosts=2,
            ),
        ]

        assert result == expected_result
