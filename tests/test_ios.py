import aiohttp
import pytest
import subprocess
import json
from unittest.mock import patch, MagicMock
from aioresponses import aioresponses
from src.Patcher.client.report_manager import ReportManager


# Test valid response - iOS device IDs
@pytest.mark.asyncio
async def test_get_device_ids_valid(
    api_client,
    mock_ios_device_id_list_response,
    mock_api_integration_response,
):
    with aioresponses() as m:
        m.get(
            url="https://mocked.url/api/v2/mobile-devices",
            payload=mock_ios_device_id_list_response,
            headers={"Accept": "application/json"},
        )
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )
        devices = await api_client.get_device_ids()

        assert len(devices) == len(mock_ios_device_id_list_response)
        assert devices[0] == mock_ios_device_id_list_response.get("results")[0]["id"]


# Test invalid response - iOS device IDs
@pytest.mark.asyncio
async def test_get_device_ids_invalid(api_client, mock_api_integration_response):
    with aioresponses() as m:
        m.get(
            url="https://mocked.url/api/v2/mobile-devices",
            payload={"invalid": "response"},
            headers={"Accept": "application/json"},
        )
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )
        devices = await api_client.get_device_ids()
        assert devices is None


# Test API error response
@pytest.mark.asyncio
async def test_get_device_ids_api_error(
    api_client,
    mock_ios_device_id_list_response,
    mock_api_integration_response,
):
    with aioresponses() as m:
        m.get(
            url="https://mocked.url/api/v2/mobile-devices",
            payload=mock_ios_device_id_list_response,
            headers={"Accept": "application/json"},
            status=401,
        )
        m.get(
            "https://mocked.url/api/v1/api-integrations",
            payload=mock_api_integration_response,
            headers={"Accept": "application/json"},
        )
        devices = await api_client.get_device_ids()
        assert devices is None
        assert pytest.raises(aiohttp.ClientError)


# Test valid response - Getting iOS Versions
@pytest.mark.asyncio
async def test_get_ios_versions_valid(
    api_client, mock_ios_detail_response, mock_api_integration_response
):
    device_ids = [1]

    with aioresponses() as m:
        for device_id in device_ids:
            m.get(
                url=f"https://mocked.url/api/v2/mobile-devices/{device_id}/detail",
                payload=mock_ios_detail_response,
                headers={"Accept": "application/json"},
            )
            m.get(
                "https://mocked.url/api/v1/api-integrations",
                payload=mock_api_integration_response,
                headers={"Accept": "application/json"},
            )

        fetched_devices = await api_client.get_device_os_versions(device_ids)

    assert fetched_devices[0].get("SN") == mock_ios_detail_response.get("serialNumber")
    assert fetched_devices[0].get("OS") == mock_ios_detail_response.get("osVersion")


# Test unauthorized API response
@pytest.mark.asyncio
async def test_get_ios_version_api_error(
    api_client, mock_ios_detail_response, mock_api_integration_response
):
    device_ids = [1]

    with aioresponses() as m:
        for device_id in device_ids:
            m.get(
                url="https://mocked.url/api/v2/mobile-devices/{device_id}/detail",
                payload=mock_ios_detail_response,
                headers={"Accept": "application/json"},
                status=401,
            )
            m.get(
                "https://mocked.url/api/v1/api-integrations",
                payload=mock_api_integration_response,
                headers={"Accept": "application/json"},
            )

        await api_client.get_device_os_versions(device_ids=device_ids)

    assert pytest.raises(aiohttp.ClientError)


# Test SOFA functionality with valid response
@patch("subprocess.run")
def test_sofa_valid(mock_run, api_client, mock_sofa_response):
    mock_run.return_value = MagicMock(
        stdout=json.dumps(mock_sofa_response), returncode=0
    )
    result = api_client.get_sofa_feed()
    expected_result = [
        {"OSVersion": "17", "ProductVersion": "17.5.1", "ReleaseDate": "May 20 2024"},
        {"OSVersion": "16", "ProductVersion": "16.7.8", "ReleaseDate": "May 13 2024"},
    ]
    assert result == expected_result


# Test subprocess error handling
@patch("subprocess.run")
def test_get_sofa_feed_subprocess_error(mock_run, api_client):
    mock_run.side_effect = subprocess.CalledProcessError(1, "curl")
    result = api_client.get_sofa_feed()
    assert result is None
    assert pytest.raises(subprocess.CalledProcessError)


# Test JSON decoding error handling
@patch("subprocess.run")
def test_get_sofa_feed_json_decode_error(mock_run, api_client):
    mock_run.return_value = MagicMock(stdout="Invalid JSON", returncode=0)
    result = api_client.get_sofa_feed()
    assert result is None
    assert pytest.raises(json.JSONDecodeError)


# Test successful calculation
@pytest.mark.asyncio
async def test_calculate_ios_on_latest_success(patcher_instance):
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
    with patch.object(patcher_instance, "log", MagicMock()):
        result = patcher_instance.calculate_ios_on_latest(
            device_versions, latest_versions
        )
    expected_result = [
        {
            "software_title": "iOS 17.5.1",
            "patch_released": "2024-05-20T00:00:00Z",
            "hosts_patched": 2,
            "missing_patch": 0,
            "completion_percent": 100.0,
            "total_hosts": 2,
        },
        {
            "software_title": "iOS 16.7.8",
            "patch_released": "2024-05-13T00:00:00Z",
            "hosts_patched": 1,
            "missing_patch": 0,
            "completion_percent": 100.0,
            "total_hosts": 1,
        },
    ]

    assert result == expected_result


# Test no devices on the latest version
@pytest.mark.asyncio
async def test_calculate_ios_on_latest_no_devices_on_latest(patcher_instance):
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
    with patch.object(patcher_instance, "log", MagicMock()):
        result = patcher_instance.calculate_ios_on_latest(
            device_versions, latest_versions
        )
    expected_result = [
        {
            "software_title": "iOS 17.5.1",
            "patch_released": "2024-05-20T00:00:00Z",
            "hosts_patched": 0,
            "missing_patch": 1,
            "completion_percent": 0.0,
            "total_hosts": 1,
        },
        {
            "software_title": "iOS 16.7.8",
            "patch_released": "2024-05-13T00:00:00Z",
            "hosts_patched": 0,
            "missing_patch": 1,
            "completion_percent": 0.0,
            "total_hosts": 1,
        },
    ]

    assert result == expected_result


# Test all devices on the latest version
@pytest.mark.asyncio
async def test_calculate_ios_on_latest_all_devices_on_latest(patcher_instance):
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

    with patch.object(patcher_instance, "log", MagicMock()):
        result = patcher_instance.calculate_ios_on_latest(
            device_versions, latest_versions
        )
    expected_result = [
        {
            "software_title": "iOS 17.5.1",
            "patch_released": "2024-05-20T00:00:00Z",
            "hosts_patched": 2,
            "missing_patch": 0,
            "completion_percent": 100.0,
            "total_hosts": 2,
        }
    ]

    assert result == expected_result


# Test some devices on the latest version
@pytest.mark.asyncio
async def test_calculate_ios_on_latest_some_devices_on_latest(patcher_instance):
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

    with patch.object(patcher_instance, "log", MagicMock()):
        result = patcher_instance.calculate_ios_on_latest(
            device_versions, latest_versions
        )
    expected_result = [
        {
            "software_title": "iOS 17.5.1",
            "patch_released": "2024-05-20T00:00:00Z",
            "hosts_patched": 1,
            "missing_patch": 1,
            "completion_percent": 50.0,
            "total_hosts": 2,
        }
    ]

    assert result == expected_result
