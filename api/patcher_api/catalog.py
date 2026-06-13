"""
Catalog version token for the ``/apps*`` ETag.

The token is the catalog's newest mutation timestamp (see
:func:`patcher_api.queries.catalog_last_mutation`) rendered as a string. It
changes exactly when the served data changes and never otherwise, so it's an
ideal cache key for both Cloudflare and revalidating clients. Computed once at
startup (the daily refresh restarts the service) and again after the macOS
resolver upload, then cached on ``app.state.catalog_version`` so the middleware
reads it without a per-request DB hit.

Lives in its own module so both :mod:`patcher_api.main` and the admin route can
use it without importing each other (``main`` imports the routers).
"""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from patcher_api.queries import catalog_last_mutation


async def recompute_catalog_version(app: FastAPI, session: AsyncSession) -> str | None:
    """
    Recompute the catalog version token and cache it on ``app.state.catalog_version``.

    Returns the new token, or ``None`` for an empty catalog (state left
    untouched). Called at startup and after any live write so the ``/apps*``
    ETag reflects the current data instead of pinning to the token captured when
    the process booted.
    """
    mutation = await catalog_last_mutation(session)
    if mutation is None:
        return None
    token = str(mutation.timestamp())
    app.state.catalog_version = token
    return token
