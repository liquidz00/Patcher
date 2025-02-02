import plistlib
import threading
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
import pytz
from src.patcher.client import BaseAPIClient
from src.patcher.client.api_client import ApiClient
from src.patcher.client.report_manager import ReportManager
from src.patcher.client.token_manager import TokenManager
from src.patcher.models.jamf_client import JamfClient
from src.patcher.models.patch import PatchTitle
from src.patcher.models.token import AccessToken
from src.patcher.utils.data_manager import DataManager


@pytest.fixture
def mock_policy_response():
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
    def get_iso_format(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    yield [
        {
            "softwareTitleId": "3",
            "softwareTitleConfigurationId": "3",
            "title": "Google Chrome",
            "latestVersion": "122.0.6261.57",
            "releaseDate": get_iso_format(datetime.now(pytz.utc) - timedelta(days=3)),
            "upToDate": 23,
            "outOfDate": 163,
            "onDashboard": True,
        },
        {
            "softwareTitleId": "4",
            "softwareTitleConfigurationId": "4",
            "title": "Jamf Connect",
            "latestVersion": "2.32.0",
            "releaseDate": get_iso_format(datetime.now(pytz.utc) - timedelta(hours=24)),
            "upToDate": 185,
            "outOfDate": 19,
            "onDashboard": True,
        },
        {
            "softwareTitleId": "5",
            "softwareTitleConfigurationId": "5",
            "title": "Apple macOS Ventura",
            "latestVersion": "13.6.4 (22G513)",
            "releaseDate": get_iso_format(datetime.now(pytz.utc) - timedelta(days=7)),
            "upToDate": 6,
            "outOfDate": 5,
            "onDashboard": True,
        },
    ]


@pytest.fixture
def mock_patch_title_response():
    def get_iso_format(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S%z")

    yield [
        PatchTitle(
            title="Google Chrome",
            title_id="3",
            released=get_iso_format(datetime.now(pytz.utc) - timedelta(days=3)),
            hosts_patched=23,
            missing_patch=163,
            latest_version="2.0.0",
        ),
        PatchTitle(
            title="Jamf Connect",
            title_id="4",
            released=get_iso_format(datetime.now(pytz.utc) - timedelta(hours=24)),
            hosts_patched=185,
            missing_patch=19,
            latest_version="1.4.5",
        ),
        PatchTitle(
            title="Apple macOS Ventura",
            title_id="5",
            released=get_iso_format(datetime.now(pytz.utc) - timedelta(days=7)),
            hosts_patched=6,
            missing_patch=5,
            latest_version="13.7.1",
        ),
    ]


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
def mock_access_token():
    return AccessToken(token="mocked_token", expires=datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def mock_jamf_client():
    return JamfClient(
        client_id="mocked_client_id",
        client_secret="mocked_client_secret",
        server="https://mocked.url",
    )


@pytest.fixture
def config_manager():
    mock_config = MagicMock()
    mock_config.get_credential.side_effect = lambda key: {
        "TOKEN": "mocked_token",
        "TOKEN_EXPIRATION": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "CLIENT_ID": "mock_client_id",
        "CLIENT_SECRET": "mock_client_secret",
        "URL": "https://mocked.url",
    }.get(key, None)
    return mock_config


@pytest.fixture(scope="function", autouse=True)
def stop_event_fixture():
    stop_event = threading.Event()
    yield stop_event
    stop_event.set()


@pytest.fixture
def patcher_instance(mock_policy_response, mock_patch_title_response):
    api_client = AsyncMock()

    api_client.get_policies.return_value = mock_policy_response
    api_client.get_summaries.return_value = mock_patch_title_response

    data_manager = MagicMock()
    pdf_report = MagicMock()

    return ReportManager(
        api_client=api_client,
        data_manager=data_manager,
        pdf_report=pdf_report,
        debug=True,
    )


@pytest.fixture
def token_manager(config_manager, mock_access_token):
    token_manager = TokenManager(config_manager)
    token_manager._token = mock_access_token
    return token_manager


@pytest.fixture
def base_api_client():
    return BaseAPIClient(max_concurrency=3)


@pytest.fixture
def mock_data_manager():
    d = DataManager(disable_cache=True)
    return MagicMock(return_value=d)


@pytest.fixture
def api_client(config_manager):
    return ApiClient(
        config=config_manager,
        concurrency=10,
    )


@pytest.fixture
def sample_patch_reports():
    return [
        PatchTitle(
            title="Example Software",
            title_id="0",
            released="2024-01-01",
            hosts_patched=10,
            missing_patch=2,
            latest_version="1.1.4",
            completion_percent=83.33,
            total_hosts=12,
        )
    ]


@pytest.fixture
def temp_output_dir(tmpdir):
    return str(tmpdir)


@pytest.fixture
def temp_output_path(tmpdir):
    return Path(tmpdir)


@pytest.fixture
def mock_plist():
    with patch("plistlib.load"), patch("plistlib.dump"):
        yield


@pytest.fixture
def mock_os_path():
    with patch("os.path.exists"), patch("os.makedirs"):
        yield


@pytest.fixture
def mock_open_file():
    with patch("builtins.open", mock_open()):
        yield


@pytest.fixture
def mock_click():
    with patch("click.prompt"), patch("click.confirm"):
        yield


@pytest.fixture
def ui_config():
    return MagicMock()


@pytest.fixture
def mock_plist_file(request):
    first_run_done_value = request.param
    plist_data = {"first_run_done": first_run_done_value}
    plist_bytes = plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)

    mock_file = BytesIO(plist_bytes)

    with (
        patch("builtins.open", return_value=mock_file),
        patch("os.path.exists", return_value=True),
        patch("os.path.expanduser", return_value="/mock/path/to/plist"),
    ):
        yield first_run_done_value
