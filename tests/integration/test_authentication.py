"""
Integration test: authenticate against a real Jamf Pro instance.

This is the foundation of the integration test suite. If this test fails,
either:
  - The integration scaffolding (fixtures, marker config) is broken, OR
  - The auth flow against the target instance is broken, OR
  - The target instance (default: dummy.jamfcloud.com) is unreachable.

Any of those invalidates the rest of the integration suite, so this test
runs first by virtue of being the smallest meaningful smoke check.
"""

from __future__ import annotations

import pytest
from src.patcher.core.models.token import AccessToken


@pytest.mark.integration
@pytest.mark.asyncio
async def test_can_fetch_token_from_dummy_instance(integration_token_manager) -> None:
    """
    The basic→bearer OAuth flow succeeds against the configured Jamf instance.

    Validates the full chain:
      ConfigManager (in-memory) →
        TokenManager.fetch_token() →
          HTTPClient.fetch_json() →
            POST /api/oauth/token →
              AccessToken parsed and returned.
    """
    token = await integration_token_manager.fetch_token()

    assert token is not None
    assert isinstance(token, AccessToken)
    assert token.token, "Token string should be non-empty"
    # Note: don't use `is_expired` here — it has a 60-second proactive-refresh
    # buffer for production callers. The dummy instance issues short-lived
    # tokens for which `is_expired` returns True even when the token is still
    # valid for ~30s. `seconds_remaining > 0` is the right smoke check: "we
    # received a token whose expiration is in the future."
    assert token.seconds_remaining > 0, (
        f"Token expiration should be in the future, got {token.seconds_remaining}s remaining "
        f"(expires at {token.expires.isoformat()})"
    )
