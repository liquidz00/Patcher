import pytest
import os
import logging
import threading
from datetime import datetime, timezone
from src.client.config_manager import ConfigManager
from src.client.patcher import Patcher
from io import StringIO
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
def mock_env_vars():
    env_vars = {
        "URL": "https://mocked.url",
        "CLIENT_ID": "mocked_client_id",
        "CLIENT_SECRET": "mocked_client_secret",
        "TOKEN": "mocked_token",
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def mock_api_integration_response():
    return {
        "totalCount": 3,
        "results": [
            {
                "authorizationScopes": ["Read Computers", "Read Computer Groups"],
                "displayName": "captain-falcon",
                "enabled": True,
                "accessTokenLifetimeSeconds": 15780000,
                "id": 3,
                "appType": "CLIENT_CREDENTIALS",
                "clientId": "a1234567-abcd-1234-efgh-123456789abc",
            },
            {
                "authorizationScopes": ["Read Computers"],
                "displayName": "enrollmentCheck",
                "enabled": True,
                "accessTokenLifetimeSeconds": 15780000,
                "id": 5,
                "appType": "CLIENT_CREDENTIALS",
                "clientId": "b2345678-bcde-2345-fghi-23456789abcd",
            },
            {
                "authorizationScopes": [
                    "Read FileVault Recovery Key",
                    "Read Computers",
                    "Read Computer Groups",
                ],
                "displayName": "api-test",
                "enabled": True,
                "accessTokenLifetimeSeconds": 1800,
                "id": 6,
                "appType": "CLIENT_CREDENTIALS",
                "clientId": "c3456789-cdef-3456-ghij-3456789abcde",
            },
        ],
    }


@pytest.fixture
def mock_lifetime_response():
    return {
        "totalCount": 1,
        "results": [
            {
                "authorizationScopes": ["Read Computers"],
                "displayName": "short-lived-token",
                "enabled": True,
                "accessTokenLifetimeSeconds": 30,
                "id": 7,
                "appType": "CLIENT_CREDENTIALS",
                "clientId": "short-lived-client-id",
            }
        ],
    }


@pytest.fixture
def mock_ios_device_id_list_response():
    return {
        "totalCount": 2,
        "results": [
            {
                "id": 1,
                "name": "iPad",
                "device_name": "iPad",
                "udid": "00008030-001D64322168202E",
                "serial_number": "XFERF6UPC4",
                "phone_number": "",
                "wifi_mac_address": "A4:FC:14:B6:50:3E",
                "managed": True,
                "supervised": True,
                "model": "iPad 9th generation (Wi-Fi)",
                "model_identifier": "iPad12,1",
                "modelDisplay": "iPad 9th generation (Wi-Fi)",
                "model_display": "iPad 9th generation (Wi-Fi)",
                "username": "",
            },
            {
                "id": 2,
                "name": "STG -M4FHF4FYDL",
                "device_name": "STG -M4FHF4FYDL",
                "udid": "00008103-000928C13C3A001E",
                "serial_number": "M4FHF4FYDL",
                "phone_number": "",
                "wifi_mac_address": "B0:E5:F9:8D:55:02",
                "managed": True,
                "supervised": True,
                "model": "iPad Pro (11-inch) (3rd generation)",
                "model_identifier": "iPad13,4",
                "modelDisplay": "iPad Pro (11-inch) (3rd generation)",
                "model_display": "iPad Pro (11-inch) (3rd generation)",
                "username": "",
            },
        ],
    }


@pytest.fixture
def mock_ios_detail_response():
    return {
        "id": "1",
        "name": "Jon's iPad",
        "enforceName": False,
        "assetTag": "12345",
        "lastInventoryUpdateTimestamp": "2018-10-15T16:39:56Z",
        "osVersion": "11.4",
        "osBuild": "15F79",
        "osSupplementalBuildVersion": "20B101",
        "osRapidSecurityResponse": "(a)",
        "softwareUpdateDeviceId": "J132AP",
        "serialNumber": "DMQVGC0DHLF0",
        "udid": "0dad565fb40b010a9e490440188063a378721069",
        "ipAddress": "10.0.0.1",
        "wifiMacAddress": "ee:00:7c:f0:e5:ff",
        "bluetoothMacAddress": "ee:00:7c:f0:e5:aa",
        "managed": True,
        "timeZone": "Europe/Warsaw",
        "initialEntryTimestamp": "2018-10-15T16:39:56.307Z",
        "lastEnrollmentTimestamp": "2018-10-15T16:39:56.307Z",
        "mdmProfileExpirationTimestamp": "2018-10-15T16:39:56.307Z",
        "deviceOwnershipLevel": "institutional",
        "enrollmentMethod": "User-initiated - no invitation",
        "enrollmentSessionTokenValid": False,
        "declarativeDeviceManagementEnabled": True,
        "site": {"id": "1", "name": "Eau Claire"},
        "extensionAttributes": [
            {
                "id": "1",
                "name": "Example EA",
                "type": "STRING",
                "value": ["EA Value"],
                "extensionAttributeCollectionAllowed": False,
            }
        ],
        "type": "ios",
        "managementId": "73226fb6-61df-4c10-9552-eb9bc353d507",
    }


@pytest.fixture
def mock_sofa_response():
    return {
        "UpdateHash": "",
        "OSVersions": [
            {
                "OSVersion": "17",
                "Latest": {
                    "ProductVersion": "17.5.1",
                    "Build": "21F6090",
                    "ReleaseDate": "2024-05-20T00:00:00Z",
                    "ExpirationDate": "2024-09-05T00:00:00Z",
                },
            },
            {
                "OSVersion": "16",
                "Latest": {
                    "ProductVersion": "16.7.8",
                    "Build": "20H6343",
                    "ReleaseDate": "2024-05-13T00:00:00Z",
                    "ExpirationDate": "2024-09-05T00:00:00Z",
                },
            },
        ],
    }


@pytest.fixture
def capture_logs():
    log_capture = logging.getLogger("patcher")
    log_capture.setLevel(logging.DEBUG)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    log_capture.addHandler(handler)

    yield stream

    log_capture.removeHandler(handler)
    handler.close()


@pytest.fixture
def config_manager():
    with patch("src.client.config_manager.keyring.get_password") as mock_get_password:

        def side_effect(service_name, key):
            if key == "TOKEN":
                return "mocked_token"
            elif key == "TOKEN_EXPIRATION":
                return datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
            elif key == "URL":
                return "https://mocked.url"
            elif key == "CLIENT_ID":
                return "a1234567-abcd-1234-efgh-123456789abc"
            return "mocked_value"

        mock_get_password.side_effect = side_effect
        managers = ConfigManager(service_name="patcher")
        yield managers


@pytest.fixture(scope="function", autouse=True)
def stop_event_fixture():
    stop_event = threading.Event()
    yield stop_event
    stop_event.set()


@pytest.fixture
def patcher_instance(mock_policy_response, mock_summary_response):
    config = MagicMock()
    ui_config = MagicMock()
    token_manager = AsyncMock()
    api_client = AsyncMock()

    api_client.get_policies.return_value = mock_policy_response
    api_client.get_summaries.return_value = mock_summary_response

    excel_report = MagicMock()
    pdf_report = MagicMock()

    return Patcher(
        config=config,
        token_manager=token_manager,
        api_client=api_client,
        excel_report=excel_report,
        pdf_report=pdf_report,
        ui_config=ui_config,
        debug=True,
    )


@pytest.fixture
def sample_patch_reports():
    return [
        {
            "software_title": "Example Software",
            "patch_released": "2024-01-01",
            "hosts_patched": 10,
            "missing_patch": 2,
            "completion_percent": 83.33,
            "total_hosts": 12,
        }
    ]


@pytest.fixture
def temp_output_dir(tmpdir):
    return str(tmpdir)
