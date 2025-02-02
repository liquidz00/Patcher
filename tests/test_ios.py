import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.patcher.models.patch import PatchTitle
from src.patcher.utils import exceptions


# Test valid response - iOS device IDs
@pytest.mark.asyncio
async def test_get_device_ids_valid(api_client, mock_ios_device_id_list_response):
    mock_body = json.dumps(mock_ios_device_id_list_response)
    mock_stdout = f"{mock_body}\nSTATUS:200".encode("utf-8")
    mock_process = AsyncMock()

    mock_process.communicate.return_value = (mock_stdout, b"")  # Bytes for stderr
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        devices = await api_client.get_device_ids()

        assert devices is not None
        assert len(devices) == len(mock_ios_device_id_list_response["results"])
        assert devices[0] == mock_ios_device_id_list_response.get("results")[0]["id"]


# Test invalid response - iOS device IDs
@pytest.mark.asyncio
async def test_get_device_ids_invalid(api_client):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = ('{"invalid": "response"}'.encode("utf-8"), b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.APIResponseError) as excinfo:
            await api_client.get_device_ids()

        assert "Failed parsing JSON response from API" in str(excinfo.value)


# Test API error response
@pytest.mark.asyncio
async def test_get_device_ids_api_error(api_client):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = ('{"error": "Unauthorized"}'.encode("utf-8"), b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.APIResponseError):
            await api_client.get_device_ids()


# Test valid response - Getting iOS Versions
@pytest.mark.asyncio
async def test_get_ios_versions_valid(api_client, mock_ios_detail_response):
    device_ids = [1]
    mock_body = json.dumps(mock_ios_detail_response)
    mock_stdout = f"{mock_body}\nSTATUS:200".encode("utf-8")
    mock_process = AsyncMock()

    mock_process.communicate.return_value = (mock_stdout, b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        fetched_devices = await api_client.get_device_os_versions(device_ids)

    assert fetched_devices[0].get("SN") == mock_ios_detail_response.get("serialNumber")
    assert fetched_devices[0].get("OS") == mock_ios_detail_response.get("osVersion")


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
        result = patcher_instance.calculate_ios_on_latest(device_versions, latest_versions)
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
        result = patcher_instance.calculate_ios_on_latest(device_versions, latest_versions)
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
        result = patcher_instance.calculate_ios_on_latest(device_versions, latest_versions)
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
        result = patcher_instance.calculate_ios_on_latest(device_versions, latest_versions)
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
