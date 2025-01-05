import json
from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.utils import exceptions


# Test getting policies (success, error)
@pytest.mark.asyncio
async def test_get_policies(api_client, mock_policy_response):
    mock_body = json.dumps(mock_policy_response)
    mock_stdout = f"{mock_body}\nSTATUS:200".encode("utf-8")

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (mock_stdout, b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        policies = await api_client.get_policies()

        assert len(policies) == len(mock_policy_response)
        assert policies[0] == mock_policy_response[0]["id"]


@pytest.mark.asyncio
async def test_get_policies_invalid_response(api_client):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = ('{"invalid": "response"}'.encode("utf-8"), b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.APIResponseError) as excinfo:
            await api_client.get_policies()

        assert "Failed parsing JSON response from API" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_policies_error(api_client):
    mock_body = '{"httpStatus": 401, "errors": []}'
    mock_stdout = f"{mock_body}\nSTATUS:401".encode("utf-8")

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (mock_stdout, b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.APIResponseError):
            await api_client.get_policies()


# Test getting summaries (success, error)
@pytest.mark.asyncio
async def test_get_summaries(api_client, mock_summary_response):
    mock_body = json.dumps(mock_summary_response)
    mock_stdout = f"{mock_body}\nSTATUS:200".encode("utf-8")

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (mock_stdout, b"")
    mock_process.returncode = 0

    with patch.object(api_client, "fetch_json", side_effect=mock_summary_response):
        summaries = await api_client.get_summaries(["3", "4", "5"])

        assert summaries[0].title == "Google Chrome"
        assert summaries[1].hosts_patched == 185
        assert summaries[2].completion_percent == 54.55


@pytest.mark.asyncio
async def test_get_summaries_error(api_client):
    mock_body = '{"httpStatus": 401, "errors": []}'
    mock_stdout = f"{mock_body}\nSTATUS:405".encode("utf-8")

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (mock_stdout, b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.APIResponseError):
            await api_client.get_summaries(["1", "2", "3"])
