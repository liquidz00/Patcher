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


# Pagination — six seed apps ordered by slug: firefox, google-chrome,
# microsoft-edge, slack, vscode, zoom.


@pytest.mark.asyncio
async def test_list_apps_limit_caps_results(client):
    response = await client.get("/apps", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # Ordered by slug, so the first two alphabetically.
    assert [record["slug"] for record in body] == ["firefox", "google-chrome"]


@pytest.mark.asyncio
async def test_list_apps_offset_skips_results(client):
    response = await client.get("/apps", params={"offset": 4})

    body = response.json()
    assert [record["slug"] for record in body] == ["vscode", "zoom"]


@pytest.mark.asyncio
async def test_list_apps_limit_and_offset_compose(client):
    response = await client.get("/apps", params={"limit": 2, "offset": 2})

    body = response.json()
    assert [record["slug"] for record in body] == ["microsoft-edge", "slack"]


@pytest.mark.asyncio
async def test_list_apps_default_returns_all_when_under_limit(client):
    """With only 6 seed apps, the default limit of 100 returns everything."""
    response = await client.get("/apps")

    body = response.json()
    assert len(body) == 6


@pytest.mark.asyncio
async def test_list_apps_rejects_limit_below_one(client):
    response = await client.get("/apps", params={"limit": 0})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_apps_rejects_limit_above_max(client):
    response = await client.get("/apps", params={"limit": 1001})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_apps_rejects_negative_offset(client):
    response = await client.get("/apps", params={"offset": -1})

    assert response.status_code == 422


# ETag + Cache-Control headers — derived from the catalog file's SHA-256
# computed at API startup. ASGITransport doesn't run lifespan by default,
# so tests inject a synthetic hash directly into app.state.


@pytest.fixture
def fixed_catalog_sha(monkeypatch):
    """Pin a deterministic catalog hash so ETag assertions are stable."""
    from patcher_api.main import app as fastapi_app

    sha = "a" * 64
    monkeypatch.setattr(fastapi_app.state, "catalog_sha", sha, raising=False)
    return sha


@pytest.mark.asyncio
async def test_etag_present_on_apps_response(client, fixed_catalog_sha):
    response = await client.get("/apps?limit=3")

    assert response.status_code == 200
    assert response.headers["etag"] == f'W/"{fixed_catalog_sha}"'
    assert "max-age=300" in response.headers["cache-control"]
    assert "stale-while-revalidate=3600" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_etag_returns_304_on_if_none_match(client, fixed_catalog_sha):
    response = await client.get(
        "/apps?limit=3",
        headers={"If-None-Match": f'W/"{fixed_catalog_sha}"'},
    )

    assert response.status_code == 304
    assert response.headers["etag"] == f'W/"{fixed_catalog_sha}"'
    assert response.text == ""


@pytest.mark.asyncio
async def test_etag_returns_full_body_on_if_none_match_mismatch(client, fixed_catalog_sha):
    """If the client's cached ETag doesn't match the live one, send the body."""
    response = await client.get(
        "/apps?limit=3",
        headers={"If-None-Match": 'W/"deadbeef"'},
    )

    assert response.status_code == 200
    assert response.json()  # non-empty body


@pytest.mark.asyncio
async def test_etag_absent_when_catalog_sha_unset(client, monkeypatch):
    """First boot pre-catalog or test transports without lifespan: no ETag."""
    from patcher_api.main import app as fastapi_app

    monkeypatch.setattr(fastapi_app.state, "catalog_sha", None, raising=False)

    response = await client.get("/apps?limit=3")

    assert response.status_code == 200
    assert "etag" not in response.headers


@pytest.mark.asyncio
async def test_etag_not_applied_to_health(client, fixed_catalog_sha):
    """/health is an ops endpoint; should always return fresh, no caching."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert "etag" not in response.headers


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
    # Regression: the endpoint must wire jamf_app_installer into the response,
    # not just installomator/homebrew_cask/autopkg (it was silently dropped).
    assert body["jamf_app_installer"]["title"] == "Mozilla Firefox"


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
    assert response.json() == {
        "installomator": None,
        "homebrew_cask": None,
        "autopkg": None,
        "mas": None,
        "jamf_app_installer": None,
    }


@pytest.mark.asyncio
async def test_get_app_sources_returns_404_for_unknown_slug(client):
    response = await client.get("/apps/nonexistent/sources")

    assert response.status_code == 404


def test_autopkg_recipe_entry_tolerates_null_name_and_shortname():
    """
    Regression: shared-processor and some app recipes carry null name /
    shortname upstream, which stitch stores faithfully. The response schema
    must accept them or /apps/{slug}/sources 500s for any app whose matched
    recipes lack one (caught on `privileges`).
    """
    from patcher_api.schemas.sources import AppSources, AutopkgRecipeEntry

    entry = AutopkgRecipeEntry.model_validate(
        {
            "identifier": "com.github.autopkg.download.Foo",
            "name": None,
            "shortname": None,
            "repo": "autopkg/foo",
            "path": "Foo/Foo.download.recipe",
        }
    )
    assert entry.name is None
    assert entry.shortname is None

    sources = AppSources.model_validate({"autopkg": {"recipes": [entry.model_dump()]}})
    assert sources.autopkg.recipes[0].shortname is None


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
    assert content["name"] == "Mozilla Firefox"
    assert content["expectedTeamID"] == "43AQ936H96"
    assert content["appNewVersion"] == "121.0"


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
async def test_generate_label_succeeds_for_jai_only_app(client, test_session):
    """
    Endpoint accepts a JAI-only app (no Installomator, no Cask) and produces a
    partial label with JAI-sourced fields. Regression test for the guard
    relaxation — the old guard rejected JAI-only apps with 422.
    """
    from patcher_api.models.app import App as AppRow
    from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow

    app_row = AppRow(
        slug="chatgpt-atlas-test",
        bundle_id="com.openai.atlas",
        name="ChatGPT Atlas",
        current_version="1.0.0",
        download_url="https://vendor.example/ChatGPT-Atlas.pkg",
        install_method=None,
        sources=["jamf_app_installer"],
    )
    test_session.add(app_row)
    await test_session.flush()  # populates app_row.id
    test_session.add(
        AppSourceDetailRow(
            app_id=app_row.id,
            installomator=None,
            homebrew_cask=None,
            autopkg=None,
            jamf_app_installer={
                "title": "ChatGPT Atlas",
                "source": "External",
                "host": "vendor.example",
                "bundle_id": "com.openai.atlas",
                "version": "1.0.0",
                "jamf_id": "999",
                "download_url": "https://vendor.example/ChatGPT-Atlas.pkg",
                "architecture": "universal",
            },
        )
    )
    await test_session.commit()

    response = await client.post("/apps/chatgpt-atlas-test/generate-label")

    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["jamf_app_installer"]
    content = body["content"]
    assert content["name"] == "ChatGPT Atlas"
    assert content["downloadURL"] == "https://vendor.example/ChatGPT-Atlas.pkg"
    assert content["packageID"] == "com.openai.atlas"
    # JAI can't carry the vendor Team ID — warning still fires.
    assert "expectedTeamID" not in content
    assert any("expectedTeamID" in w for w in body["warnings"])
