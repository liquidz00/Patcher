from unittest.mock import AsyncMock, patch

import pytest
from src.patcher.utils import exceptions


# Tests for constructors and property getters
@pytest.mark.asyncio
async def test_constructor_and_property(base_api_client):
    assert base_api_client.max_concurrency == 3
    assert base_api_client.concurrency == 3
    assert base_api_client.default_headers == {
        "accept": "application/json",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_set_concurrency(base_api_client):
    base_api_client.concurrency = 2
    assert base_api_client.concurrency == 2

    with pytest.raises(exceptions.PatcherError):
        base_api_client.concurrency = 0


# Test command execution
@pytest.mark.asyncio
async def test_execute(base_api_client):
    command = ["echo", "test"]
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"output", b"")
    mock_process.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        result = await base_api_client.execute(command)

        assert result == "output"


@pytest.mark.asyncio
async def test_execute_failure(base_api_client):
    command = ["invalid_command"]
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"", b"error")
    mock_process.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with pytest.raises(exceptions.ShellCommandError):
            await base_api_client.execute(command)


# Test HTTP Status code handling
def test_handle_status_code_success(base_api_client):
    response_json = {"data": "test"}
    result = base_api_client._handle_status_code(200, response_json)
    assert result == response_json


def test_handle_status_code_client_error(base_api_client):
    with pytest.raises(exceptions.APIResponseError):
        base_api_client._handle_status_code(404, {"errors": "Not Found"})


def test_handle_status_code_server_error(base_api_client):
    with pytest.raises(exceptions.APIResponseError):
        base_api_client._handle_status_code(500, {"errors": "Server Error"})


# Test JSON fetching
@pytest.mark.asyncio
async def test_fetch_json(base_api_client):
    with patch.object(
        base_api_client, "execute", AsyncMock(return_value='{"key": "value"}\nSTATUS:200')
    ) as mock_execute:
        result = await base_api_client.fetch_json("https://example.com/api")
        assert result == {"key": "value"}
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_json_failure(base_api_client):
    with patch.object(
        base_api_client, "execute", AsyncMock(return_value='{"errors": "error"}\nSTATUS:500')
    ):
        with pytest.raises(exceptions.APIResponseError):
            await base_api_client.fetch_json("https://example.com/api")


# Test batch fetching
@pytest.mark.asyncio
async def test_fetch_batch(base_api_client):
    with patch.object(
        base_api_client, "fetch_json", AsyncMock(side_effect=[{"data": 1}, {"data": 2}])
    ):
        urls = ["https://example.com/api/1", "https://example.com/api/2"]
        results = await base_api_client.fetch_batch(urls)
        assert results == [{"data": 1}, {"data": 2}]


# Test setup calls
@pytest.mark.asyncio
async def test_fetch_basic_token(base_api_client):
    with patch.object(
        base_api_client, "execute", AsyncMock(return_value='{"token": "abc123"}')
    ) as mock_execute:
        result = await base_api_client.fetch_basic_token("user", "pass", "https://example.com")
        assert result == "abc123"
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_roles(base_api_client):
    with patch.object(
        base_api_client,
        "execute",
        AsyncMock(return_value='{"displayName": "Patcher-Role"}\nSTATUS:200'),
    ) as mock_execute:
        result = await base_api_client.create_roles("token", "https://example.com")
        assert result is True
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_client(base_api_client):
    with patch.object(
        base_api_client,
        "execute",
        AsyncMock(
            side_effect=[
                '{"clientId": "123", "id": "456"}\nSTATUS:200',
                '{"clientSecret": "secret"}\nSTATUS:200',
            ]
        ),
    ) as mock_execute:
        result = await base_api_client.create_client("token", "https://example.com")
        assert result == ("123", "secret")
        assert mock_execute.call_count == 2
