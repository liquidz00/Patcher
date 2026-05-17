"""
Jamf App Installers catalog ingestion.

Fetches the public HTML table at ``learn.jamf.com``, parses out each
title's name, source (``"Jamf"`` or ``"External"``), and host, and
upserts the result into the ``jamf_app_installers`` table.

The upstream "API" here is a documentation page that renders the catalog
inside a HTML ``<table>``. There is no JSON endpoint and no authentication
required. The unlisted Jamf Pro API endpoint that exposes richer metadata
(bundle_id, version, download URL, Software Title ID) requires an
authenticated tenant, which Patcher's catalog ingest does not have access
to. When that changes, this module gets a second fetch path and the
model + stitch logic gain the additional columns.

**Parsing strategy:** the table cells use a stable ``headers`` attribute
keyed to the column header IDs (``reference-7022__entry__1`` for the
title name, ``__entry__2`` for source, ``__entry__3`` for host). A small
regex picks those out of the HTML directly. Less fragile than full DOM
parsing for what's effectively a three-column flat table; surfaces a
zero-row result if Jamf restructures the page, which the script logs as
a warning rather than failing silently.
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.models.jamf_app_installers import JamfAppInstaller
from patcher_api.schemas.jamf_app_installers import JamfAppInstallerRow

JAMF_APP_INSTALLERS_URL = (
    "https://learn.jamf.com/api/khub/maps/cOCaZK_7gN_vt9d~S6Ez4A/"
    "topics/cQ9wyPB40Qwip7o1wEd1iA/content?target=DESIGNED_READER"
    "&v=aa70f9de69380c359c3a82776da44127"
)

# The HTML table cells carry a ``headers`` attribute pointing at the
# column header IDs. ``__entry__1`` is title, ``__entry__2`` is source,
# ``__entry__3`` is host. We anchor on this attribute rather than the
# generic ``<td>`` because the page contains other tables and prose we
# don't want to scrape into the catalog.
_CELL_PATTERN = re.compile(
    r'headers="reference-7022__entry__([123])">([^<]*)</td>',
    re.DOTALL,
)

# Upstream's placeholder for "Jamf-hosted, no external host" is the
# literal string "--". We normalize that to ``None`` at the boundary so
# downstream queries don't have to special-case it.
_NO_HOST_PLACEHOLDER = "--"

log = logging.getLogger(__name__)


async def fetch_jamf_app_installers_html(
    client: httpx.AsyncClient | None = None,
) -> str:
    """
    Fetch the upstream HTML catalog page.

    :param client: Optional pre-configured ``httpx.AsyncClient``. If
        ``None``, a new client with a 30-second timeout is created and
        disposed of before returning.
    :type client: httpx.AsyncClient | None
    :return: The raw HTML response body.
    :rtype: str
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        response = await client.get(JAMF_APP_INSTALLERS_URL)
        response.raise_for_status()
        return response.text
    finally:
        if owns_client:
            await client.aclose()


def parse_jamf_app_installers_table(html: str) -> list[dict[str, Any]]:
    """
    Parse the upstream HTML into a list of row dicts.

    Cells are matched by their ``headers`` attribute and grouped in
    chunks of three (one chunk per row). Rows with the wrong number of
    cells (a damaged upstream record) are skipped and logged.

    :param html: Raw HTML response from
        :func:`fetch_jamf_app_installers_html`.
    :type html: str
    :return: List of ``{"title": ..., "source": ..., "host": ...}``
        dicts. ``host`` is ``None`` when upstream's value was the
        ``"--"`` placeholder.
    :rtype: list[dict[str, Any]]
    """
    matches = _CELL_PATTERN.findall(html)
    if len(matches) % 3 != 0:
        log.warning(
            "Cell count %d is not divisible by 3; upstream table may be malformed",
            len(matches),
        )

    rows: list[dict[str, Any]] = []
    current: dict[str, str] = {}
    for column, value in matches:
        value = value.strip()
        if column == "1":
            if current:
                log.warning("Incomplete JAI row, skipping: %r", current)
            current = {"title": value}
        elif column == "2":
            current["source"] = value
        elif column == "3":
            host = None if value == _NO_HOST_PLACEHOLDER else value
            current["host"] = host
            rows.append(current)
            current = {}

    if current:
        log.warning("Trailing incomplete JAI row, skipping: %r", current)

    return rows


async def ingest_jamf_app_installers(
    session: AsyncSession,
    parsed_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Upsert parsed JAI rows into the ``jamf_app_installers`` table.

    Records that fail Pydantic validation (e.g. unexpected ``source``
    value) are logged and skipped; ingestion continues for the rest.

    :param session: Async SQLAlchemy session bound to the target DB.
    :type session: sqlalchemy.ext.asyncio.AsyncSession
    :param parsed_rows: List of row dicts from
        :func:`parse_jamf_app_installers_table`.
    :type parsed_rows: list[dict[str, Any]]
    :return: ``(ingested, skipped)``.
    :rtype: tuple[int, int]
    """
    ingested = skipped = 0

    for row in parsed_rows:
        try:
            record = JamfAppInstallerRow.model_validate(row)
        except ValidationError as exc:
            log.warning("Skipping JAI row %r: %s", row.get("title"), exc)
            skipped += 1
            continue

        now = datetime.now(UTC)
        stmt = insert(JamfAppInstaller).values(
            title=record.title,
            source=record.source,
            host=record.host,
            raw=row,
            ingested_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["title"],
            set_={
                "source": stmt.excluded.source,
                "host": stmt.excluded.host,
                "raw": stmt.excluded.raw,
                "ingested_at": stmt.excluded.ingested_at,
            },
        )
        await session.execute(stmt)
        ingested += 1

    await session.commit()
    return ingested, skipped
