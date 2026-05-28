"""
Jamf App Installers catalog ingestion.

Pulls Jamf Pro's App Installers *titles* API (OAuth client credentials) and
upserts each title into the ``jamf_app_installers`` table. The title endpoints
are catalog-global — they return the same data on any instance, including
Jamf's public dummy instance — so no specific tenant is required.

- :func:`fetch_jai_titles` — the title list (lean records carrying ``bundle_id``
  + ``version``).
- :func:`fetch_jai_catalog` — list plus bounded-concurrency per-title detail
  (download URLs, architecture), one token for the whole sweep.
- :func:`ingest_jai_titles` — upsert fetched titles, deriving ``source``/``host``
  from each title's media source.
"""

import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.jamf_app_installers import JamfAppInstaller
from patcher_api.schemas.jamf_app_installers import JaiTitle, JaiTitlePage

# Jamf Pro App Installers titles API. OAuth client-credentials token, then a
# paginated sweep of the global title catalog.
_JAI_OAUTH_PATH = "/api/oauth/token"
_JAI_TITLES_PATH = "/api/v1/app-installers/titles"
_JAI_PAGE_SIZE = 200
# Bounded fan-out for per-title detail calls — enough to finish the ~few-hundred
# titles inside the short token life, gentle enough not to trip rate limits.
_JAI_DETAIL_CONCURRENCY = 10

log = logging.getLogger(__name__)


async def _fetch_jai_token(
    client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str
) -> str:
    """Exchange OAuth client credentials for a Jamf Pro bearer token (short-lived)."""
    response = await client.post(
        f"{base_url}{_JAI_OAUTH_PATH}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "grant_type": "client_credentials",
            "client_secret": client_secret,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _auth_headers(
    client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str
) -> dict[str, str]:
    """Bearer auth headers for the titles API (one token covers a full sweep)."""
    token = await _fetch_jai_token(client, base_url, client_id, client_secret)
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def _paginate_titles(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str]
) -> list[JaiTitle]:
    """Page through the titles list until ``totalCount`` is reached (lean records)."""
    titles: list[JaiTitle] = []
    page = 0
    while True:
        response = await client.get(
            f"{base_url}{_JAI_TITLES_PATH}",
            headers=headers,
            params={"page": page, "page-size": _JAI_PAGE_SIZE},
        )
        response.raise_for_status()
        parsed = JaiTitlePage.model_validate(response.json())
        titles.extend(parsed.results)
        if not parsed.results or len(titles) >= parsed.total_count:
            break
        page += 1
    return titles


async def fetch_jai_titles(
    base_url: str,
    client_id: str,
    client_secret: str,
    client: httpx.AsyncClient | None = None,
) -> list[JaiTitle]:
    """
    Fetch the App Installers title catalog (lean list records only).

    Authenticates once, then pages through ``GET /api/v1/app-installers/titles``.
    The list records carry ``bundle_id`` + ``version`` (enough for stitching) but
    not per-title download URLs or architecture — use :func:`fetch_jai_catalog`
    for those.

    :param base_url: Jamf Pro base URL (e.g. ``https://dummy.jamfcloud.com``).
        Any instance works — the title endpoints serve the global catalog.
    :type base_url: str
    :param client_id: OAuth API client ID.
    :type client_id: str
    :param client_secret: OAuth API client secret.
    :type client_secret: str
    :param client: Optional pre-configured ``httpx.AsyncClient``.
    :type client: httpx.AsyncClient | None
    :return: Every catalog title as lean :class:`JaiTitle` records.
    :rtype: list[:class:`JaiTitle`]
    :raises httpx.HTTPError: On auth failure or a non-2xx page response.
    """
    base_url = base_url.rstrip("/")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        headers = await _auth_headers(client, base_url, client_id, client_secret)
        titles = await _paginate_titles(client, base_url, headers)
        log.info("Fetched %d Jamf App Installer titles from %s", len(titles), base_url)
        return titles
    finally:
        if owns_client:
            await client.aclose()


async def fetch_jai_catalog(
    base_url: str,
    client_id: str,
    client_secret: str,
    *,
    concurrency: int = _JAI_DETAIL_CONCURRENCY,
    client: httpx.AsyncClient | None = None,
) -> list[JaiTitle]:
    """
    Fetch the full catalog with per-title detail (download URLs, architecture).

    One token for the whole sweep: list the titles, then fan out the per-title
    detail GETs under a bounded semaphore. The list + parallel detail finish in
    a few seconds — comfortably inside the token's short life — so no re-auth is
    needed. A title whose detail fetch fails (e.g. a 429 that survives one retry)
    falls back to its lean list record, which still carries ``bundle_id`` +
    ``version``; the run never aborts over one bad title.

    :param base_url: Jamf Pro base URL. Any instance works (catalog-global).
    :type base_url: str
    :param client_id: OAuth API client ID.
    :type client_id: str
    :param client_secret: OAuth API client secret.
    :type client_secret: str
    :param concurrency: Max in-flight detail requests.
    :type concurrency: int
    :param client: Optional pre-configured ``httpx.AsyncClient``.
    :type client: httpx.AsyncClient | None
    :return: Every catalog title, detail-enriched where the detail call succeeded.
    :rtype: list[:class:`JaiTitle`]
    """
    base_url = base_url.rstrip("/")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    semaphore = asyncio.Semaphore(concurrency)

    async def detail(title: JaiTitle) -> JaiTitle:
        async with semaphore:
            for attempt in range(2):
                response = await client.get(
                    f"{base_url}{_JAI_TITLES_PATH}/{title.id}", headers=headers
                )
                if response.status_code == 429 and attempt == 0:
                    await asyncio.sleep(float(response.headers.get("Retry-After", 2)))
                    continue
                response.raise_for_status()
                return JaiTitle.model_validate(response.json())
            response.raise_for_status()  # second 429: surface it (caught below)
            return title

    try:
        headers = await _auth_headers(client, base_url, client_id, client_secret)
        lean = await _paginate_titles(client, base_url, headers)

        results = await asyncio.gather(*(detail(t) for t in lean), return_exceptions=True)
        enriched: list[JaiTitle] = []
        failures = 0
        for lean_title, result in zip(lean, results):
            if isinstance(result, Exception):
                failures += 1
                enriched.append(lean_title)
            else:
                enriched.append(result)
        if failures:
            log.warning("JAI detail: %d/%d titles fell back to lean records", failures, len(lean))
        log.info("Fetched %d Jamf App Installer titles (detailed) from %s", len(enriched), base_url)
        return enriched
    finally:
        if owns_client:
            await client.aclose()


async def ingest_jai_titles(
    session: AsyncSession,
    titles: list[JaiTitle],
) -> tuple[int, int]:
    """
    Upsert API-fetched titles into ``jamf_app_installers`` (keyed by title name).

    Derives ``source``/``host`` from the title's media source so API rows carry
    the same coverage fields the HTML scrape provides, plus the enrichment
    columns (``bundle_id``/``version``/``jamf_id``/``download_url``/
    ``architecture``). The full title payload is preserved in ``raw``.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param titles: Title records from :func:`fetch_jai_catalog` (or
        :func:`fetch_jai_titles`).
    :type titles: list[:class:`JaiTitle`]
    :return: ``(ingested, skipped)``.
    :rtype: tuple[int, int]
    """
    ingested = 0
    for title in titles:
        source = "Jamf" if (title.media_source_type or "").upper() == "JAMF_SERVER" else "External"
        download_url = title.media_sources[0].url if title.media_sources else None
        host = (
            httpx.URL(download_url).host or None
            if (source == "External" and download_url)
            else None
        )

        now = datetime.now(UTC)
        stmt = insert(JamfAppInstaller).values(
            title=title.title_name,
            source=source,
            host=host,
            bundle_id=title.bundle_id,
            version=title.version or title.short_version,
            jamf_id=title.id,
            download_url=download_url,
            architecture=title.architecture,
            raw=title.model_dump(mode="json", by_alias=True),
            ingested_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["title"],
            set_={
                "source": stmt.excluded.source,
                "host": stmt.excluded.host,
                "bundle_id": stmt.excluded.bundle_id,
                "version": stmt.excluded.version,
                "jamf_id": stmt.excluded.jamf_id,
                "download_url": stmt.excluded.download_url,
                "architecture": stmt.excluded.architecture,
                "raw": stmt.excluded.raw,
                "ingested_at": stmt.excluded.ingested_at,
            },
        )
        await session.execute(stmt)
        ingested += 1

    await session.commit()
    return ingested, 0
