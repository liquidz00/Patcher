from unittest.mock import AsyncMock, Mock, patch

import httpx
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


# ---------------------------------------------------------------------- #
# httpx transport: `http` property, `aclose`, `fetch_text`
#
# These tests cover the new httpx-backed surface added alongside the
# existing curl-based methods. Existing tests above are unchanged: the
# curl path is still in place during the migration.
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_http_property_lazy_init(base_api_client):
    """First access constructs the AsyncClient; second access returns the same instance."""
    assert base_api_client._http_client is None
    first = base_api_client.http
    assert isinstance(first, httpx.AsyncClient)
    second = base_api_client.http
    assert first is second  # cached on the instance
    await base_api_client.aclose()


@pytest.mark.asyncio
async def test_aclose_is_idempotent(base_api_client):
    """aclose() is safe to call multiple times and resets the lazy-init state."""
    # Force construction
    _ = base_api_client.http
    assert base_api_client._http_client is not None
    await base_api_client.aclose()
    assert base_api_client._http_client is None
    # Second call no-ops
    await base_api_client.aclose()
    assert base_api_client._http_client is None


@pytest.mark.asyncio
async def test_fetch_text_returns_body_on_2xx(base_api_client):
    """A 2xx response returns the response body as text."""
    mock_response = Mock(status_code=200, is_success=True, text="hello world")
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    base_api_client._http_client = mock_http

    result = await base_api_client.fetch_text("https://example.com")

    assert result == "hello world"
    mock_http.get.assert_called_once_with("https://example.com", headers=None)


@pytest.mark.asyncio
async def test_fetch_text_passes_headers_through(base_api_client):
    """Custom headers are forwarded verbatim to httpx.get."""
    mock_response = Mock(status_code=200, is_success=True, text="ok")
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    base_api_client._http_client = mock_http

    headers = {"Authorization": "Bearer abc"}
    await base_api_client.fetch_text("https://example.com", headers=headers)
    mock_http.get.assert_called_once_with("https://example.com", headers=headers)


@pytest.mark.asyncio
async def test_fetch_text_raises_with_not_found_flag_on_404(base_api_client):
    """404 → APIResponseError with not_found=True, matching fetch_json's contract."""
    mock_response = Mock(status_code=404, is_success=False)
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    base_api_client._http_client = mock_http

    with pytest.raises(exceptions.APIResponseError) as exc_info:
        await base_api_client.fetch_text("https://example.com/missing")

    assert getattr(exc_info.value, "not_found", False) is True


@pytest.mark.asyncio
async def test_fetch_text_raises_on_5xx(base_api_client):
    """5xx → APIResponseError without the not_found flag."""
    mock_response = Mock(status_code=503, is_success=False)
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    base_api_client._http_client = mock_http

    with pytest.raises(exceptions.APIResponseError) as exc_info:
        await base_api_client.fetch_text("https://example.com")

    assert getattr(exc_info.value, "not_found", False) is False


@pytest.mark.asyncio
async def test_fetch_text_raises_on_network_error(base_api_client):
    """httpx.RequestError → APIResponseError with a 'Network error' message."""
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=httpx.ConnectError("connect failed"))
    base_api_client._http_client = mock_http

    with pytest.raises(exceptions.APIResponseError, match="Network error"):
        await base_api_client.fetch_text("https://unreachable.example.com")
