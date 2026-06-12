from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from src.patcher.core import exceptions


# Tests for constructors and property getters
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_constructor_and_property(self, http_client):
        assert http_client.max_concurrency == 3
        assert http_client.default_headers == {
            "accept": "application/json",
            "Content-Type": "application/json",
        }

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self, http_client):
        """aclose() is safe to call multiple times and resets the lazy-init state."""
        # Force construction
        _ = http_client.http
        assert http_client._http_client is not None
        await http_client.aclose()
        assert http_client._http_client is None
        # Second call no-ops
        await http_client.aclose()
        assert http_client._http_client is None


# Test HTTP Status code handling
class TestRaiseForStatus:
    def test_raise_for_status_success_is_noop(self, http_client):
        """2xx responses do not raise; the caller is responsible for returning the body."""
        assert http_client._raise_for_status(200, {"data": "test"}) is None

    def test_raise_for_status_404_sets_not_found_flag(self, http_client):
        with pytest.raises(exceptions.APIResponseError) as exc_info:
            http_client._raise_for_status(404, {"errors": "Not Found"})
        assert getattr(exc_info.value, "not_found", False) is True

    def test_raise_for_status_client_error(self, http_client):
        with pytest.raises(exceptions.APIResponseError):
            http_client._raise_for_status(400, {"errors": "Bad Request"})

    def test_raise_for_status_server_error(self, http_client):
        with pytest.raises(exceptions.APIResponseError):
            http_client._raise_for_status(500, {"errors": "Server Error"})


# Test JSON fetching
class TestFetchJson:
    @pytest.mark.asyncio
    async def test_fetch_json(self, http_client):
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {"key": "value"}
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        result = await http_client.fetch_json("https://example.com/api")

        assert result == {"key": "value"}
        mock_http.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_json_failure(self, http_client):
        """A 5xx response is translated to APIResponseError via _raise_for_status."""
        mock_response = Mock(status_code=500)
        mock_response.json.return_value = {"errors": "error"}
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        with pytest.raises(exceptions.APIResponseError):
            await http_client.fetch_json("https://example.com/api")

    @pytest.mark.asyncio
    async def test_fetch_batch(self, http_client):
        with patch.object(
            http_client, "fetch_json", AsyncMock(side_effect=[{"data": 1}, {"data": 2}])
        ):
            urls = ["https://example.com/api/1", "https://example.com/api/2"]
            results = await http_client.fetch_batch(urls)
            assert results == [{"data": 1}, {"data": 2}]


# Test setup calls
class TestHttpProperty:
    @pytest.mark.asyncio
    async def test_http_property_lazy_init(self, http_client):
        """First access constructs the AsyncClient; second access returns the same instance."""
        assert http_client._http_client is None
        first = http_client.http
        assert isinstance(first, httpx.AsyncClient)
        second = http_client.http
        assert first is second  # cached on the instance
        await http_client.aclose()

    @pytest.mark.asyncio
    async def test_http_property_uses_truststore_ssl_context(self, http_client):
        """
        The lazy http client is configured with a truststore-backed SSLContext.

        Asserts the wire-in, not truststore itself — we trust the library to do
        its job; we just verify Patcher hands httpx an OS-trust-store SSL context
        rather than relying on httpx's certifi default.
        """
        import ssl

        import truststore

        client = http_client.http
        # httpx stores the verify argument; we check that we passed an SSLContext
        # constructed via truststore, not the default True (certifi).
        assert isinstance(client._transport._pool._ssl_context, ssl.SSLContext)
        # truststore subclasses ssl.SSLContext, so identity check via class:
        assert isinstance(client._transport._pool._ssl_context, truststore.SSLContext)
        await http_client.aclose()


class TestFetchText:
    @pytest.mark.asyncio
    async def test_fetch_text_returns_body_on_2xx(self, http_client):
        """A 2xx response returns the response body as text."""
        mock_response = Mock(status_code=200, is_success=True, text="hello world")
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        result = await http_client.fetch_text("https://example.com")

        assert result == "hello world"
        mock_http.get.assert_called_once_with("https://example.com", headers=None, params=None)

    @pytest.mark.asyncio
    async def test_fetch_text_passes_headers_through(self, http_client):
        """Custom headers are forwarded verbatim to httpx.get."""
        mock_response = Mock(status_code=200, is_success=True, text="ok")
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        headers = {"Authorization": "Bearer abc"}
        await http_client.fetch_text("https://example.com", headers=headers)
        mock_http.get.assert_called_once_with("https://example.com", headers=headers, params=None)

    @pytest.mark.asyncio
    async def test_fetch_text_passes_params_through(self, http_client):
        """Query params (dict and list-of-tuples) are forwarded verbatim to httpx.get."""
        mock_response = Mock(status_code=200, is_success=True, text="ok")
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        # list-of-tuples form is required by Jamf's CSV export endpoint, which
        # repeats the same `columns-to-export` key for each desired column.
        params = [("columns-to-export", "computerName"), ("columns-to-export", "deviceId")]
        await http_client.fetch_text("https://example.com", params=params)
        mock_http.get.assert_called_once_with("https://example.com", headers=None, params=params)

    @pytest.mark.asyncio
    async def test_fetch_text_raises_with_not_found_flag_on_404(self, http_client):
        """404 → APIResponseError with not_found=True, matching fetch_json's contract."""
        mock_response = Mock(status_code=404, is_success=False)
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        with pytest.raises(exceptions.APIResponseError) as exc_info:
            await http_client.fetch_text("https://example.com/missing")

        assert getattr(exc_info.value, "not_found", False) is True

    @pytest.mark.asyncio
    async def test_fetch_text_raises_on_5xx(self, http_client):
        """5xx → APIResponseError without the not_found flag."""
        mock_response = Mock(status_code=503, is_success=False)
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        http_client._http_client = mock_http

        with pytest.raises(exceptions.APIResponseError) as exc_info:
            await http_client.fetch_text("https://example.com")

        assert getattr(exc_info.value, "not_found", False) is False

    @pytest.mark.asyncio
    async def test_fetch_text_raises_on_network_error(self, http_client):
        """httpx.RequestError → APIResponseError with a 'Network error' message."""
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("connect failed"))
        http_client._http_client = mock_http

        with pytest.raises(exceptions.APIResponseError, match="Network error"):
            await http_client.fetch_text("https://unreachable.example.com")
