"""
API clients for Patcher.

``HTTPClient`` (the concurrency-limited, truststore-TLS async base) lives in
:mod:`patcher.clients.http_client` and is re-exported here so the established
``from patcher.clients import HTTPClient`` import keeps working. The
per-service clients live in their own modules (``jamf``, ``installomator``,
``patcher_api``, ``token_manager``).
"""

from .http_client import HTTPClient

__all__ = ["HTTPClient"]
