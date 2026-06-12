"""
Tests for the MCP server tools.

Exercises each tool through fastmcp's in-process ``Client`` transport so the
full MCP protocol path runs (initialization, tool discovery, dispatch,
result encoding) without spinning up uvicorn. Tools acquire their own DB
sessions via :func:`get_session_maker`, which the ``mcp_session`` fixture
monkeypatches to point at the test engine.
"""

import json

import pytest
import pytest_asyncio
from fastmcp import Client
from patcher_api.mcp import mcp
from patcher_api.models.app import App as AppRow
from patcher_api.models.app import AppSourceDetail as AppSourceDetailRow
from sqlalchemy.ext.asyncio import async_sessionmaker

from patcher.catalog import InstallMethod


@pytest_asyncio.fixture
async def mcp_session(monkeypatch, test_engine):
    """
    Session against the test engine, with the tools module's reference to
    :func:`get_session_maker` patched so any tool invocation hits the same
    engine. Yields the session unseeded for tests to populate explicitly.
    """
    session_maker = async_sessionmaker(test_engine, expire_on_commit=False)
    # Both the tools and resources modules import get_session_maker into their
    # own namespace, so each reference is patched to hit the test engine.
    monkeypatch.setattr(
        "patcher_api.mcp.tools.get_session_maker",
        lambda: session_maker,
    )
    monkeypatch.setattr(
        "patcher_api.mcp.resources.get_session_maker",
        lambda: session_maker,
    )
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def mcp_client(mcp_session):
    """In-process MCP Client bound to the patched test engine."""
    async with Client(mcp) as client:
        yield client


async def _add_app(
    session,
    *,
    slug: str,
    name: str | None = None,
    vendor: str | None = None,
    bundle_id: str | None = None,
    current_version: str | None = None,
    install_method: str | None = None,
    sources: list[str] | None = None,
    installomator: dict | None = None,
    homebrew_cask: dict | None = None,
    jamf_app_installer: dict | None = None,
    autopkg: dict | None = None,
) -> AppRow:
    """Insert a minimal AppRow + optional source detail. Commits before returning."""
    app = AppRow(
        slug=slug,
        name=name or slug.title(),
        vendor=vendor,
        bundle_id=bundle_id,
        current_version=current_version,
        install_method=install_method,
        sources=sources or [],
    )
    session.add(app)
    await session.flush()  # populate app.id for the FK below

    if any(p is not None for p in (installomator, homebrew_cask, jamf_app_installer, autopkg)):
        session.add(
            AppSourceDetailRow(
                app_id=app.id,
                installomator=installomator,
                homebrew_cask=homebrew_cask,
                jamf_app_installer=jamf_app_installer,
                autopkg=autopkg,
            )
        )
    await session.commit()
    return app


async def _add_drift_pair(
    session,
    slug: str,
    *,
    installomator_version: str,
    cask_version: str,
    vendor: str | None = None,
) -> AppRow:
    """
    Insert an app with both Installomator and Homebrew Cask source data so
    that :func:`patcher_api.drift.extract_versions` finds two versioned
    sources to compare.
    """
    return await _add_app(
        session,
        slug=slug,
        name=slug.title(),
        vendor=vendor,
        sources=["installomator", "homebrew_cask"],
        installomator={
            "label_name": slug,
            "raw": {"appNewVersion": installomator_version},
        },
        homebrew_cask={"token": slug, "cask_json": {"version": cask_version}},
    )


@pytest.mark.asyncio
async def test_protocol_lists_all_registered_tools(mcp_client):
    """The in-process Client can discover every tool through the protocol."""
    tools = await mcp_client.list_tools()
    names = {t.name for t in tools}
    assert {
        "get_catalog_summary",
        "search_apps",
        "get_app",
        "list_drift",
        "list_categories",
        "generate_installomator_label",
        "get_app_sources",
        "list_recent_changes",
    } <= names


@pytest.mark.asyncio
async def test_get_catalog_summary_on_empty_catalog(mcp_client):
    """Empty catalog returns zeros for every counter, not None or missing keys."""
    result = await mcp_client.call_tool("get_catalog_summary", {})
    assert result.is_error is False
    assert result.data == {
        "total_apps": 0,
        "sources": {
            "installomator": 0,
            "homebrew_cask": 0,
            "jamf_app_installer": 0,
            "autopkg": 0,
        },
    }


@pytest.mark.asyncio
async def test_get_catalog_summary_counts_per_source(mcp_session, mcp_client):
    """
    Per-source counts reflect which source-detail JSON columns are populated;
    an app with no source detail still counts toward total_apps but zero on
    every per-source bucket.
    """
    await _add_app(
        mcp_session,
        slug="firefox",
        installomator={"label_name": "firefox"},
        homebrew_cask={"token": "firefox"},
    )
    await _add_app(
        mcp_session,
        slug="slack",
        homebrew_cask={"token": "slack"},
        jamf_app_installer={"title": "Slack"},
    )
    # No source detail at all — bumps total_apps but contributes to no bucket.
    await _add_app(mcp_session, slug="bare-app")

    result = await mcp_client.call_tool("get_catalog_summary", {})

    assert result.data == {
        "total_apps": 3,
        "sources": {
            "installomator": 1,
            "homebrew_cask": 2,
            "jamf_app_installer": 1,
            "autopkg": 0,
        },
    }


@pytest.mark.asyncio
async def test_search_apps_matches_name_case_insensitive(mcp_session, mcp_client):
    """ILIKE means an uppercase query still hits a lowercase-stored value."""
    await _add_app(mcp_session, slug="firefox", name="Firefox", vendor="Mozilla")

    result = await mcp_client.call_tool("search_apps", {"query": "FIRE"})

    assert result.is_error is False
    assert len(result.data) == 1
    assert result.data[0]["slug"] == "firefox"


@pytest.mark.asyncio
async def test_search_apps_matches_vendor_and_bundle_id(mcp_session, mcp_client):
    """A query that matches only on vendor or bundle_id still surfaces the app."""
    await _add_app(
        mcp_session,
        slug="atlas",
        name="ChatGPT Atlas",
        vendor="OpenAI",
        bundle_id="com.openai.atlas",
    )

    by_vendor = await mcp_client.call_tool("search_apps", {"query": "openai"})
    assert [a["slug"] for a in by_vendor.data] == ["atlas"]

    by_bundle_id = await mcp_client.call_tool("search_apps", {"query": "com.openai"})
    assert [a["slug"] for a in by_bundle_id.data] == ["atlas"]


@pytest.mark.asyncio
async def test_search_apps_orders_by_slug_and_caps_at_limit(mcp_session, mcp_client):
    """Determinism: results come back slug-ordered, with limit clamped to 100."""
    for slug in ("zoom", "alfred", "magnet"):
        await _add_app(mcp_session, slug=slug, name=slug.title())

    # All three match an empty query; limit=2 returns the slug-ordered first two.
    result = await mcp_client.call_tool("search_apps", {"query": "", "limit": 2})
    assert [a["slug"] for a in result.data] == ["alfred", "magnet"]


@pytest.mark.asyncio
async def test_search_apps_returns_empty_list_on_no_match(mcp_session, mcp_client):
    """No match is an empty list, not an error."""
    await _add_app(mcp_session, slug="firefox")

    result = await mcp_client.call_tool("search_apps", {"query": "chromium"})

    assert result.is_error is False
    assert result.data == []


@pytest.mark.asyncio
async def test_get_app_returns_full_record(mcp_session, mcp_client):
    """get_app returns every field the public App schema exposes."""
    await _add_app(
        mcp_session,
        slug="firefox",
        name="Firefox",
        vendor="Mozilla",
        bundle_id="org.mozilla.firefox",
        current_version="121.0",
        install_method="dmg",
        sources=["installomator", "homebrew_cask"],
    )

    result = await mcp_client.call_tool("get_app", {"slug": "firefox"})

    assert result.is_error is False
    assert result.data["slug"] == "firefox"
    assert result.data["name"] == "Firefox"
    assert result.data["vendor"] == "Mozilla"
    assert result.data["bundle_id"] == "org.mozilla.firefox"
    assert result.data["current_version"] == "121.0"
    assert result.data["install_method"] == "dmg"
    assert result.data["sources"] == ["installomator", "homebrew_cask"]


@pytest.mark.asyncio
async def test_get_app_signals_error_on_unknown_slug(mcp_client):
    """Unknown slug raises ValueError in-tool, surfaces as a protocol error result."""
    with pytest.raises(Exception) as excinfo:
        await mcp_client.call_tool("get_app", {"slug": "does-not-exist"})
    assert "does-not-exist" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_drift_finds_disagreement(mcp_session, mcp_client):
    """When two versioned sources report different versions, drift is detected."""
    await _add_drift_pair(
        mcp_session, "firefox", installomator_version="121.0", cask_version="120.0"
    )

    result = await mcp_client.call_tool("list_drift", {})

    assert result.is_error is False
    assert result.data["total_scanned"] == 1
    assert result.data["total_with_drift"] == 1
    entry = result.data["entries"][0]
    assert entry["slug"] == "firefox"
    assert entry["leader"] == "installomator"
    assert entry["laggard"] == "homebrew_cask"
    assert {v["source"] for v in entry["versions"]} == {"installomator", "homebrew_cask"}


@pytest.mark.asyncio
async def test_list_drift_excludes_agreement(mcp_session, mcp_client):
    """Apps where sources agree are scanned but absent from entries."""
    await _add_drift_pair(
        mcp_session, "chrome", installomator_version="120.0", cask_version="120.0"
    )

    result = await mcp_client.call_tool("list_drift", {})

    assert result.data["total_scanned"] == 1
    assert result.data["total_with_drift"] == 0
    assert result.data["entries"] == []


@pytest.mark.asyncio
async def test_list_drift_respects_vendor_filter(mcp_session, mcp_client):
    """Vendor filter narrows results before drift computation."""
    await _add_drift_pair(
        mcp_session,
        "firefox",
        installomator_version="121.0",
        cask_version="120.0",
        vendor="Mozilla",
    )
    await _add_drift_pair(
        mcp_session,
        "slack",
        installomator_version="4.32.0",
        cask_version="4.31.0",
        vendor="Slack",
    )

    result = await mcp_client.call_tool("list_drift", {"vendor": "Mozilla"})

    assert result.data["total_with_drift"] == 1
    assert result.data["entries"][0]["slug"] == "firefox"


@pytest.mark.asyncio
async def test_list_drift_paginates_via_limit_and_offset(mcp_session, mcp_client):
    """limit/offset slice the drift results deterministically; totals stay unpaged."""
    for slug in ("alpha", "beta", "gamma"):
        await _add_drift_pair(mcp_session, slug, installomator_version="2.0", cask_version="1.0")

    page1 = await mcp_client.call_tool("list_drift", {"limit": 2, "offset": 0})
    page2 = await mcp_client.call_tool("list_drift", {"limit": 2, "offset": 2})

    assert [e["slug"] for e in page1.data["entries"]] == ["alpha", "beta"]
    assert [e["slug"] for e in page2.data["entries"]] == ["gamma"]
    # The unpaged total is preserved across pages.
    assert page1.data["total_with_drift"] == 3
    assert page2.data["total_with_drift"] == 3


@pytest.mark.asyncio
async def test_list_categories_returns_full_install_method_enum(mcp_client):
    """install_methods always reflects the static enum, not just used values."""
    result = await mcp_client.call_tool("list_categories", {})

    assert result.is_error is False
    assert set(result.data["install_methods"]) == {m.value for m in InstallMethod}


@pytest.mark.asyncio
async def test_list_categories_returns_distinct_vendors_and_sources(mcp_session, mcp_client):
    """Vendors and sources are derived from the catalog; deduped and sorted."""
    await _add_app(mcp_session, slug="firefox", vendor="Mozilla", sources=["installomator"])
    await _add_app(
        mcp_session,
        slug="slack",
        vendor="Slack",
        sources=["installomator", "homebrew_cask"],
    )
    await _add_app(mcp_session, slug="vsc", vendor="Microsoft", sources=["homebrew_cask"])
    # An app with no vendor is silently excluded from the vendor list.
    await _add_app(mcp_session, slug="orphan", vendor=None, sources=["homebrew_cask"])

    result = await mcp_client.call_tool("list_categories", {})

    assert result.data["vendors"] == ["Microsoft", "Mozilla", "Slack"]
    assert result.data["sources"] == ["homebrew_cask", "installomator"]


@pytest.mark.asyncio
async def test_generate_installomator_label_returns_label_for_app_with_sources(
    mcp_session, mcp_client
):
    """Happy path: an app with both Installomator + Cask sources produces a complete label."""
    await _add_app(
        mcp_session,
        slug="firefox",
        name="Firefox",
        vendor="Mozilla",
        bundle_id="org.mozilla.firefox",
        current_version="121.0",
        install_method="dmg",
        sources=["installomator", "homebrew_cask"],
        installomator={
            "label_name": "firefox",
            "label_url": "https://github.com/Installomator/Installomator/labels/firefox.sh",
            "raw": {
                "name": "Firefox",
                "type": "dmg",
                "expectedTeamID": "43AQ936H96",
            },
        },
        homebrew_cask={
            "token": "firefox",
            "cask_json": {
                "name": ["Mozilla Firefox"],
                "url": "https://download.mozilla.org/firefox.dmg",
            },
        },
    )

    result = await mcp_client.call_tool("generate_installomator_label", {"slug": "firefox"})

    assert result.is_error is False
    assert result.data["label_name"] == "firefox"
    assert "installomator" in result.data["sources_used"]
    assert "homebrew_cask" in result.data["sources_used"]
    assert result.data["content"]["name"] == "Mozilla Firefox"
    assert result.data["content"]["expectedTeamID"] == "43AQ936H96"
    assert result.data["content"]["appNewVersion"] == "121.0"


@pytest.mark.asyncio
async def test_generate_installomator_label_unknown_slug_raises(mcp_client):
    """Unknown slug raises ValueError in-tool, surfaces as a protocol error result."""
    with pytest.raises(Exception) as excinfo:
        await mcp_client.call_tool("generate_installomator_label", {"slug": "does-not-exist"})
    assert "does-not-exist" in str(excinfo.value)


@pytest.mark.asyncio
async def test_generate_installomator_label_no_source_detail_raises(mcp_session, mcp_client):
    """An app with no source detail cannot produce a label; tool raises with a clear message."""
    await _add_app(mcp_session, slug="bare-app")

    with pytest.raises(Exception) as excinfo:
        await mcp_client.call_tool("generate_installomator_label", {"slug": "bare-app"})
    assert "no source detail" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_app_sources_returns_raw_payloads(mcp_session, mcp_client):
    """Tool returns each source's native shape, not the stitched canonical projection."""
    await _add_app(
        mcp_session,
        slug="firefox",
        sources=["installomator", "homebrew_cask"],
        installomator={
            "label_name": "firefox",
            "label_url": "https://github.com/Installomator/Installomator/labels/firefox.sh",
            "raw": {"expectedTeamID": "43AQ936H96"},
        },
        homebrew_cask={
            "token": "firefox",
            "cask_json": {"version": "121.0"},
        },
    )

    result = await mcp_client.call_tool("get_app_sources", {"slug": "firefox"})

    assert result.is_error is False
    assert result.data["installomator"]["label_name"] == "firefox"
    assert result.data["installomator"]["raw"]["expectedTeamID"] == "43AQ936H96"
    assert result.data["homebrew_cask"]["token"] == "firefox"
    assert result.data["homebrew_cask"]["cask_json"]["version"] == "121.0"
    assert result.data["autopkg"] is None
    assert result.data["jamf_app_installer"] is None


@pytest.mark.asyncio
async def test_get_app_sources_returns_all_none_for_app_without_sources(mcp_session, mcp_client):
    """App exists but has no source detail row: every source key is None, no error."""
    await _add_app(mcp_session, slug="bare-app")

    result = await mcp_client.call_tool("get_app_sources", {"slug": "bare-app"})

    assert result.is_error is False
    assert result.data == {
        "installomator": None,
        "homebrew_cask": None,
        "autopkg": None,
        "jamf_app_installer": None,
    }


@pytest.mark.asyncio
async def test_get_app_sources_unknown_slug_raises(mcp_client):
    """Unknown slug raises ValueError in-tool, surfaces as a protocol error result."""
    with pytest.raises(Exception) as excinfo:
        await mcp_client.call_tool("get_app_sources", {"slug": "does-not-exist"})
    assert "does-not-exist" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_recent_changes_returns_newest_first_up_to_limit(mcp_session, mcp_client):
    """Apps come back in id-desc order (newest insertion first), capped at limit."""
    for slug in ("alpha", "beta", "gamma", "delta"):
        await _add_app(mcp_session, slug=slug)

    result = await mcp_client.call_tool("list_recent_changes", {"limit": 2})

    assert result.is_error is False
    assert [a["slug"] for a in result.data] == ["delta", "gamma"]


def _resource_json(read_result) -> dict:
    """Decode a ``read_resource`` result into the JSON dict it carries."""
    contents = read_result.contents if hasattr(read_result, "contents") else read_result
    return json.loads(contents[0].text)


@pytest.mark.asyncio
async def test_protocol_lists_resources_and_prompts(mcp_client):
    """Static resources, the app template, and every prompt are discoverable."""
    resources = {str(r.uri) for r in await mcp_client.list_resources()}
    templates = {t.uriTemplate for t in await mcp_client.list_resource_templates()}
    prompts = {p.name for p in await mcp_client.list_prompts()}

    assert {"catalog://summary", "catalog://categories"} <= resources
    assert "catalog://apps/{slug}" in templates
    assert {"audit_app_coverage", "find_label_for", "catalog_health_report"} <= prompts


@pytest.mark.asyncio
async def test_summary_resource_mirrors_tool(mcp_session, mcp_client):
    """The catalog://summary resource returns the same shape as the tool."""
    await _add_app(
        mcp_session,
        slug="firefox",
        installomator={"label_name": "firefox"},
        homebrew_cask={"token": "firefox"},
    )

    data = _resource_json(await mcp_client.read_resource("catalog://summary"))

    assert data["total_apps"] == 1
    assert data["sources"]["installomator"] == 1
    assert data["sources"]["homebrew_cask"] == 1


@pytest.mark.asyncio
async def test_categories_resource_returns_distinct_values(mcp_session, mcp_client):
    """The catalog://categories resource surfaces distinct vendors and sources."""
    await _add_app(mcp_session, slug="firefox", vendor="Mozilla", sources=["installomator"])
    await _add_app(mcp_session, slug="slack", vendor="Slack", sources=["homebrew_cask"])

    data = _resource_json(await mcp_client.read_resource("catalog://categories"))

    assert data["vendors"] == ["Mozilla", "Slack"]
    assert set(data["sources"]) == {"installomator", "homebrew_cask"}
    assert "dmg" in data["install_methods"]


@pytest.mark.asyncio
async def test_app_resource_returns_record(mcp_session, mcp_client):
    """The catalog://apps/{slug} template returns the canonical app projection."""
    await _add_app(mcp_session, slug="firefox", name="Firefox", vendor="Mozilla")

    data = _resource_json(await mcp_client.read_resource("catalog://apps/firefox"))

    assert data["slug"] == "firefox"
    assert data["name"] == "Firefox"
    assert data["vendor"] == "Mozilla"


@pytest.mark.asyncio
async def test_app_resource_unknown_slug_errors(mcp_session, mcp_client):
    """An unknown slug surfaces as a protocol error naming the missing slug."""
    with pytest.raises(Exception) as excinfo:
        await mcp_client.read_resource("catalog://apps/does-not-exist")
    assert "does-not-exist" in str(excinfo.value)


@pytest.mark.asyncio
async def test_audit_prompt_interpolates_slug(mcp_client):
    """The audit prompt renders a single user message naming the slug + tools."""
    result = await mcp_client.get_prompt("audit_app_coverage", {"slug": "firefox"})

    assert len(result.messages) == 1
    assert result.messages[0].role == "user"
    text = result.messages[0].content.text
    assert "firefox" in text
    assert "get_app_sources" in text


@pytest.mark.asyncio
async def test_find_label_prompt_interpolates_name(mcp_client):
    """The label prompt renders the app name and names the generate tool."""
    result = await mcp_client.get_prompt("find_label_for", {"app_name": "Google Chrome"})

    text = result.messages[0].content.text
    assert "Google Chrome" in text
    assert "generate_installomator_label" in text


@pytest.mark.asyncio
async def test_health_report_prompt_takes_no_arguments(mcp_client):
    """The health-report prompt renders without arguments and names both tools."""
    result = await mcp_client.get_prompt("catalog_health_report", {})

    text = result.messages[0].content.text
    assert "get_catalog_summary" in text
    assert "list_categories" in text
