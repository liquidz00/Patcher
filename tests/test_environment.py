import pytest
from unittest.mock import patch, call, ANY
from bin import utils, globals


@patch("bin.utils.set_key")
def test_update_env(mock_set_key):
    token = "newToken"
    expires_in = 3600
    utils.update_env(token=token, expires_in=expires_in)

    dotenv_path = globals.ENV_PATH

    expected_calls = [
        call(
            dotenv_path=dotenv_path,
            key_to_set="TOKEN",
            value_to_set=token,
        ),
        call(
            dotenv_path=dotenv_path,
            key_to_set="TOKEN_EXPIRATION",
            value_to_set=ANY,
        ),
    ]
    mock_set_key.assert_has_calls(calls=expected_calls, any_order=True)

    assert mock_set_key.call_count == 2
