"""Default font download helper.

Pulled out of :class:`patcher.cli.ui_manager.UIConfigManager` so library
callers generating PDF reports can ensure the bundled Assistant fonts
are present on disk without instantiating the CLI's UIConfigManager
(which is plist-coupled and lives in :mod:`patcher.cli`).
"""

import ssl
from pathlib import Path

import httpx
import truststore

from .exceptions import PatcherError
from .logger import LogMe

_FONT_URLS = {
    "regular": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf",
    "bold": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf",
}


def ensure_default_fonts(target_dir: Path) -> dict[str, Path]:
    """
    Ensure the default Assistant fonts (Regular and Bold) live in ``target_dir``.

    Idempotent — fonts already present on disk are not re-downloaded. Uses
    :func:`httpx.get` configured with a :class:`truststore.SSLContext` so the
    same OS-trust-store TLS handling that powers ``BaseAPIClient`` applies
    here too (corporate-CA proxies, etc.).

    :param target_dir: Directory to drop the ``.ttf`` files into. Created
        with ``parents=True`` if missing.
    :type target_dir: Path
    :return: Mapping ``{"regular": Path, "bold": Path}`` of the on-disk
        font files.
    :rtype: dict[str, Path]
    :raises PatcherError: If a download or write fails.
    """
    log = LogMe("ensure_default_fonts")
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "regular": target_dir / "Assistant-Regular.ttf",
        "bold": target_dir / "Assistant-Bold.ttf",
    }
    if all(p.exists() for p in paths.values()):
        return paths

    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for font_type, url in _FONT_URLS.items():
        dest = paths[font_type]
        if dest.exists():
            continue
        try:
            response = httpx.get(url, verify=ctx, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            dest.write_bytes(response.content)
            log.info(f"Font saved: {dest}")
        except (httpx.HTTPError, OSError) as e:
            log.error(f"Unable to download font from {url}: {e}")
            raise PatcherError(
                "Failed to download default font family.",
                url=url,
                error_msg=str(e),
            )
    return paths
