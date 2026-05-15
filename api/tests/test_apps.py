import pytest
from patcher_api.schemas.app import InstallMethod


@pytest.mark.asyncio
async def test_list_apps_returns_seed_records(client):
    response = await client.get("/apps")

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 2
    assert all("slug" in record for record in body)


@pytest.mark.asyncio
async def test_list_apps_install_method_is_valid_enum(client):
    response = await client.get("/apps")

    valid_methods = {m.value for m in InstallMethod}
    for record in response.json():
        assert record["install_method"] in valid_methods


@pytest.mark.asyncio
async def test_list_apps_filters_by_vendor(client):
    response = await client.get("/apps", params={"vendor": "Mozilla"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["vendor"] == "Mozilla"


@pytest.mark.asyncio
async def test_list_apps_vendor_filter_is_case_insensitive(client):
    response = await client.get("/apps", params={"vendor": "mozilla"})

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_list_apps_vendor_filter_returns_multiple_matches(client):
    response = await client.get("/apps", params={"vendor": "Microsoft"})

    body = response.json()
    assert len(body) == 2
    assert {record["name"] for record in body} == {"Visual Studio Code", "Microsoft Edge"}


@pytest.mark.asyncio
async def test_list_apps_vendor_filter_with_no_matches_returns_empty(client):
    response = await client.get("/apps", params={"vendor": "Acme Corp"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_apps_filters_by_source_include(client):
    response = await client.get("/apps", params={"source": "installomator"})

    body = response.json()
    assert all("installomator" in record["sources"] for record in body)
    assert {record["slug"] for record in body} == {
        "firefox",
        "google-chrome",
        "slack",
        "zoom",
        "vscode",
    }


@pytest.mark.asyncio
async def test_list_apps_filters_by_source_exclude(client):
    response = await client.get("/apps", params={"exclude_source": "installomator"})

    body = response.json()
    assert all("installomator" not in record["sources"] for record in body)
    assert {record["slug"] for record in body} == {"microsoft-edge"}


@pytest.mark.asyncio
async def test_list_apps_source_and_exclude_compose(client):
    response = await client.get(
        "/apps",
        params={"source": "homebrew_cask", "exclude_source": "installomator"},
    )

    body = response.json()
    assert {record["slug"] for record in body} == {"microsoft-edge"}


@pytest.mark.asyncio
async def test_get_app_returns_record_for_known_slug(client):
    response = await client.get("/apps/firefox")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "firefox"
    assert body["bundle_id"] == "com.mozilla.firefox"
    assert body["name"] == "Firefox"
    assert body["vendor"] == "Mozilla"


@pytest.mark.asyncio
async def test_get_app_returns_404_for_unknown_slug(client):
    response = await client.get("/apps/nonexistent")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_app_sources_returns_populated_sources_for_firefox(client):
    response = await client.get("/apps/firefox/sources")

    assert response.status_code == 200
    body = response.json()
    assert body["installomator"]["label_name"] == "firefoxpkg"
    assert body["installomator"]["raw"]["expectedTeamID"] == "43AQ936H96"
    assert body["homebrew_cask"]["token"] == "firefox"
    assert body["autopkg"] is None


@pytest.mark.asyncio
async def test_get_app_sources_returns_homebrew_only_for_edge(client):
    response = await client.get("/apps/microsoft-edge/sources")

    body = response.json()
    assert body["installomator"] is None
    assert body["homebrew_cask"]["token"] == "microsoft-edge"


@pytest.mark.asyncio
async def test_get_app_sources_returns_empty_for_app_without_seed_sources(client):
    """
    Slack has no entry in SEED_SOURCES — endpoint should still return 200
    with all-None fields.
    """
    response = await client.get("/apps/slack/sources")

    assert response.status_code == 200
    assert response.json() == {"installomator": None, "homebrew_cask": None, "autopkg": None}


@pytest.mark.asyncio
async def test_get_app_sources_returns_404_for_unknown_slug(client):
    response = await client.get("/apps/nonexistent/sources")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_label_returns_full_label_for_app_with_both_sources(client):
    """firefox has both installomator + homebrew_cask source detail in the seed."""
    response = await client.post("/apps/firefox/generate-label")

    assert response.status_code == 200
    body = response.json()
    assert body["label_name"] == "firefox"
    assert "installomator" in body["sources_used"]
    assert "homebrew_cask" in body["sources_used"]
    content = body["content"]
    assert content.startswith("firefox)\n")
    assert 'name="Mozilla Firefox"' in content
    assert 'expectedTeamID="43AQ936H96"' in content
    assert content.rstrip().endswith(";;")


@pytest.mark.asyncio
async def test_generate_label_cask_only_app_warns_about_team_id(client):
    """microsoft-edge has homebrew_cask only — should warn that expectedTeamID is unknown."""
    response = await client.post("/apps/microsoft-edge/generate-label")

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["homebrew_cask"]
    assert "expectedTeamID" not in body["content"]
    assert any("expectedTeamID" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_generate_label_returns_404_for_unknown_slug(client):
    response = await client.post("/apps/nonexistent/generate-label")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_label_returns_422_when_app_has_no_source_detail(client):
    """slack is in SEED_APPS but has no entry in SEED_SOURCES — can't generate a label."""
    response = await client.post("/apps/slack/generate-label")

    assert response.status_code == 422
    assert "no source detail" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_label_requires_auth(unauth_client):
    response = await unauth_client.post("/apps/firefox/generate-label")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
