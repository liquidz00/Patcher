"""
Admin routes scoped to deploy-token authentication.

Distinct from the user-facing routes in ``apps.py`` — these endpoints
perform privileged operations (today: catalog upload; future: token
management, manual swap trigger) and authenticate against the separate
``deploy_tokens`` table via :func:`patcher_api.auth.get_current_deploy_token`.

A valid user token does NOT authorize these endpoints.
"""

import hashlib
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from patcher_api.auth import get_current_deploy_token
from patcher_api.config import get_settings
from patcher_api.models.deploy_token import DeployToken

log = logging.getLogger(__name__)

# Reuses the per-IP limiter registered on app.state in main.py. Generous
# enough for the daily catalog-refresh CI run plus the occasional manual
# retry, tight enough that a leaked token + brute-force loop gets shut down.
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    include_in_schema=False,
)


@router.post("/catalog/upload")
@limiter.limit("12/hour")
async def upload_catalog(
    request: Request,
    x_catalog_sha256: str | None = Header(None, alias="X-Catalog-SHA256"),
    _deploy_token: DeployToken = Depends(get_current_deploy_token),
) -> dict[str, object]:
    """
    Receive a fresh catalog DB and stage it for the swap daemon.

    The body is streamed to ``{incoming_dir}/patcher_api.db.tmp`` and
    atomically renamed to ``{incoming_dir}/patcher_api.db`` once fully
    received. A systemd.path unit on the host watches that final filename
    and triggers ``swap-patcher-catalog.sh`` to stop the API, back up the
    live DB, move the staged file into place, restore perms, and restart.

    The atomic rename matters: ``systemd.path`` fires on file changes, and
    we don't want it triggering on a half-written upload. Writing to
    ``.tmp`` then renaming guarantees the watch only sees a complete file.

    :param request: ASGI request whose body is the raw catalog DB bytes.
        Content-Type should be ``application/octet-stream``.
    :param x_catalog_sha256: Caller-computed SHA-256 of the body, used as
        an integrity check (rejects partial uploads + accidental
        corruption). Optional but strongly recommended. Hex-encoded; case
        insensitive. **This is not a security control**; the bearer-token
        auth is the security control.
    :raises HTTPException 401: missing/invalid/revoked deploy token
    :raises HTTPException 413: body exceeds ``max_upload_bytes`` setting
    :raises HTTPException 400: SHA-256 header value doesn't match body
    :return: ``{"bytes_received": int, "sha256": str, "staged_path": str}``
    """
    settings = get_settings()
    max_bytes = settings.max_upload_bytes

    # Reject up-front on advertised oversized uploads. Most well-behaved
    # clients send Content-Length; doing this check first means we never
    # allocate disk for a request we'll refuse anyway.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds maximum of {max_bytes} bytes",
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")

    settings.incoming_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = settings.incoming_dir / "patcher_api.db.tmp"
    final_path = settings.incoming_dir / "patcher_api.db"

    hasher = hashlib.sha256()
    bytes_received = 0

    try:
        with tmp_path.open("wb") as f:
            async for chunk in request.stream():
                bytes_received += len(chunk)
                if bytes_received > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds maximum of {max_bytes} bytes",
                    )
                f.write(chunk)
                hasher.update(chunk)

        actual_sha = hasher.hexdigest()
        if x_catalog_sha256 is not None:
            if x_catalog_sha256.strip().lower() != actual_sha.lower():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "X-Catalog-SHA256 header does not match computed body hash; upload rejected"
                    ),
                )

        # Atomic on the same filesystem. After this returns, systemd.path
        # sees the file change and fires the swap service.
        tmp_path.replace(final_path)
        log.info(
            "Catalog upload staged: bytes=%d sha256=%s -> %s",
            bytes_received,
            actual_sha,
            final_path,
        )
    except Exception:
        # Don't leave a half-written .tmp around to confuse future uploads
        # or to be mistaken for a real artifact.
        tmp_path.unlink(missing_ok=True)
        raise

    return {
        "bytes_received": bytes_received,
        "sha256": actual_sha,
        "staged_path": str(final_path),
    }
