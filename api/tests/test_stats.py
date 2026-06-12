import pytest


@pytest.mark.asyncio
async def test_stats_returns_catalog_summary(client):
    response = await client.get("/stats")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["total_apps"], int)
    assert set(body["sources"]) == {
        "installomator",
        "homebrew_cask",
        "jamf_app_installer",
        "autopkg",
    }
    # Present in the response even when the seed leaves them empty.
    assert "last_refresh" in body
    assert "catalog_version" in body
