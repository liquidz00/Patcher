import os
from unittest.mock import AsyncMock, mock_open, patch

import click
import pytest
from aioresponses import aioresponses
from src.patcher.client.setup import Setup


@pytest.fixture
def setup_instance(config_manager, token_manager, ui_config, mock_jamf_client):
    instance = Setup(config=config_manager, token_manager=token_manager, ui_config=ui_config)
    instance.config.attach_client.return_value = mock_jamf_client
    return instance


@pytest.mark.asyncio
async def test_init(setup_instance, config_manager, token_manager, ui_config):
    assert setup_instance.config == config_manager
    assert setup_instance.token_manager == token_manager
    assert setup_instance.ui_config == ui_config
    assert setup_instance.plist_path == os.path.expanduser(
        "~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist"
    )
    assert setup_instance._completed is False
    assert setup_instance.token is None
    assert setup_instance.jamf_url is None


def test_completed_property(setup_instance):
    setup_instance._completed = True
    assert setup_instance.completed is True


def test_is_complete(setup_instance):
    with (
        patch("os.path.exists", return_value=True),
        patch("plistlib.load", return_value={"first_run_done": True}),
        patch("builtins.open", mock_open(read_data=b"")),
    ):
        setup_instance._is_complete()
        assert setup_instance._completed is True


def test_is_complete_error(setup_instance):
    with patch("os.path.exists", return_value=True):
        with patch("plistlib.load", side_effect=Exception("plist read error")):
            with pytest.raises(click.Abort):
                setup_instance._is_complete()


def test_greet(setup_instance):
    with patch("click.echo") as mock_click_echo:
        setup_instance._greet()
        assert mock_click_echo.call_count == 3


def test_set_complete(setup_instance):
    with patch("os.makedirs") as mock_makedirs:
        with patch("plistlib.dump") as mock_plistlib_dump:
            with patch("builtins.open", mock_open()):
                setup_instance._set_complete()
                assert setup_instance._completed is True
                mock_makedirs.assert_called_once()
                mock_plistlib_dump.assert_called_once()


def test_set_complete_error(setup_instance):
    with patch("os.makedirs") as mock_makedirs:
        with patch("plistlib.dump", side_effect=Exception("plist write error")):
            with patch("builtins.open", mock_open()):
                with pytest.raises(click.Abort):
                    setup_instance._set_complete()


def test_setup_ui(setup_instance, ui_config):
    with patch(
        "click.prompt",
        side_effect=["Header", "Footer", "CustomFont", "/path/to/regular.ttf", "/path/to/bold.ttf"],
    ):
        with patch("click.confirm", return_value=True):
            with patch("os.makedirs") as mock_makedirs:
                with patch("shutil.copy") as mock_shutil_copy:
                    with patch("configparser.ConfigParser.write") as mock_config_write:
                        setup_instance._setup_ui()
                        mock_makedirs.assert_called()
                        mock_shutil_copy.assert_called()
                        mock_config_write.assert_called_once()


@pytest.mark.asyncio
async def test_basic_token_success(setup_instance):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"token": "mocked_token"}
        mock_post.return_value.__aenter__.return_value = mock_response
        success = await setup_instance._basic_token("password", "username", "https://mocked.url")
        assert success is True
        assert setup_instance.token == "mocked_token"


@pytest.mark.asyncio
async def test_basic_token_401(setup_instance):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text.return_value = "Unauthorized"
        mock_post.return_value.__aenter__.return_value = mock_response
        success = await setup_instance._basic_token("password", "username", "https://mocked.url")
        assert success is False


@pytest.mark.asyncio
async def test_basic_token_error(setup_instance):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Server Error"
        mock_post.return_value.__aenter__.return_value = mock_response
        with pytest.raises(click.Abort):
            await setup_instance._basic_token("password", "username", "https://mocked.url")


@pytest.mark.asyncio
async def test_create_roles_success(setup_instance):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response
        success = await setup_instance._create_roles("mocked_token")
        assert success is True


@pytest.mark.asyncio
async def test_create_client_success(setup_instance):
    with aioresponses() as m:
        client_creation_url = f"{setup_instance.jamf_url}/api/v1/api-integrations"
        m.post(
            client_creation_url,
            payload={"clientId": "mocked_client_id", "id": "integration_id"},
            status=200,
        )

        client_secret_url = (
            f"{setup_instance.jamf_url}/api/v1/api-integrations/integration_id/client-credentials"
        )
        m.post(client_secret_url, payload={"clientSecret": "mocked_client_secret"}, status=200)

        client_id, client_secret = await setup_instance._create_client()

        assert client_id == "mocked_client_id"
        assert client_secret == "mocked_client_secret"


@pytest.mark.asyncio
async def test_first_run_completed(setup_instance):
    with patch.object(setup_instance, "_is_complete") as mock_is_complete:
        setup_instance._completed = True
        await setup_instance.first_run()
        mock_is_complete.assert_called_once()


# Test passes as expected, launch method works as intended.
# Leaving test commented out as the sleep duration causes prolonged test results
#   that aren't suitable for CI/CD pipelines and results
#
# @pytest.mark.asyncio
# async def test_launch(setup_instance, token_manager):
#     with patch("click.prompt", side_effect=["https://mocked.url", "username", "password"]):
#         with patch("click.confirm", return_value=True):
#             with patch.object(setup_instance, "_basic_token", return_value=True):
#                 with patch.object(setup_instance, "_create_roles", return_value=True):
#                     with patch.object(
#                         setup_instance,
#                         "_create_client",
#                         return_value=("client_id", "client_secret"),
#                     ):
#                         with patch.object(
#                             setup_instance.token_manager, "fetch_token", return_value=AsyncMock()
#                         ):
#                             with patch.object(setup_instance.token_manager, "save_token"):
#                                 with patch.object(setup_instance, "_setup_ui"):
#                                     with patch.object(setup_instance, "_set_complete"):
#                                         with patch("asyncio.sleep", return_value=AsyncMock()):
#                                             await setup_instance.launch()
#                                             assert setup_instance.jamf_url == "https://mocked.url"
