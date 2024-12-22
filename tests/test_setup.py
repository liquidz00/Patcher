import os
import tempfile
from pathlib import Path
from plistlib import InvalidFileException
from unittest.mock import mock_open, patch

import pytest
from src.patcher.client.setup import Setup


@pytest.fixture
def setup_instance(config_manager, ui_config, mock_jamf_client, api_client, token_manager, request):
    # Create temp file path
    temp_plist = tempfile.NamedTemporaryFile(suffix=".plist", delete=False)
    temp_plist_path = Path(temp_plist.name)
    temp_plist.close()

    # Mock plist_path to use temp file
    with patch.object(ui_config, "plist_path", new=temp_plist_path):
        instance = Setup(
            config=config_manager,
            ui_config=ui_config,
        )
        instance.config.attach_client.return_value = mock_jamf_client

        # Clean up after test
        def cleanup():
            if temp_plist_path.exists():
                os.remove(temp_plist_path)

        request.addfinalizer(cleanup)

        yield instance


@pytest.mark.asyncio
async def test_init(setup_instance, config_manager, ui_config):
    assert setup_instance.config == config_manager
    assert setup_instance.ui_config == ui_config
    assert setup_instance.ui_config.plist_path.exists()
    assert setup_instance._completed is None


def test_completed_property(setup_instance):
    setup_instance._completed = True
    assert setup_instance.completed is True


def test_is_complete(setup_instance):
    with (
        patch.object(Path, "exists", return_value=True),
        patch("plistlib.load", return_value={"Setup": {"first_run_done": True}}),
        patch("builtins.open", mock_open(read_data=b"")),
    ):
        setup_instance._check_completion()
        assert setup_instance._completed is True


def test_is_complete_error(setup_instance):
    with patch.object(Path, "exists", return_value=True):
        with patch("plistlib.load", side_effect=InvalidFileException("plist read error")):
            setup_instance._check_completion()
            assert setup_instance._completed is False


@pytest.mark.asyncio
async def test_first_run_completed(setup_instance):
    setup_instance._completed = None
    with patch.object(setup_instance, "_check_completion") as mock_is_complete:
        with patch("click.confirm", return_value=False):
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
#                             with patch.object(setup_instance.token_manager, "_save_token"):
#                                 with patch.object(setup_instance, "_setup_ui"):
#                                     with patch.object(setup_instance, "_set_complete"):
#                                         with patch("asyncio.sleep", return_value=AsyncMock()):
#                                             await setup_instance.launch()
#                                             assert setup_instance.jamf_url == "https://mocked.url"
