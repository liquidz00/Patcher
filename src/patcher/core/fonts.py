"""
Default font management.

.. versionchanged:: 3.3.0

    Single home for font assets so library callers generating PDF reports can
    ensure the bundled Assistant fonts are present on disk without instantiating
    CLI machinery. Owns the font directory, the default font paths, the presence
    check, the download, and asset copying.
"""

import shutil
import ssl
from pathlib import Path

import httpx
import truststore

from .exceptions import PatcherError
from .logger import LogMe

FONT_DIR = Path.home() / "Library/Application Support/Patcher/fonts"

_FONT_URLS = {
    "regular": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Regular.ttf",
    "bold": "https://github.com/hafontia-zz/Assistant/raw/master/Fonts/TTF/Assistant-Bold.ttf",
}


def get_font_paths(font_dir: Path = FONT_DIR) -> dict[str, Path]:
    """On-disk paths for the bundled Assistant fonts within ``font_dir``."""
    return {
        "regular": font_dir / "Assistant-Regular.ttf",
        "bold": font_dir / "Assistant-Bold.ttf",
    }


def fonts_present(font_dir: Path = FONT_DIR) -> bool:
    """True if both Assistant fonts already exist in ``font_dir``."""
    return all(p.exists() for p in get_font_paths(font_dir).values())


def copy_asset(src: Path, dest: Path) -> None:
    """Copy a user-provided asset (custom font, branding logo) into place."""
    try:
        shutil.copy(src, dest)
    except (OSError, shutil.SameFileError) as e:
        raise PatcherError(
            "Failed to copy file as expected.",
            source=src,
            destination=dest,
            error_msg=str(e),
        )


def ensure_default_fonts(target_dir: Path = FONT_DIR) -> dict[str, Path]:
    """
    Ensure the default Assistant fonts (Regular and Bold) live in ``target_dir``.

    Idempotent. Fonts already present on disk are not re-downloaded. Uses
    :func:`httpx.get` configured with a :class:`truststore.SSLContext` so the
    same OS-trust-store TLS handling that powers ``BaseAPIClient`` applies
    here too (corporate-CA proxies, etc.).

    :param target_dir: Directory to drop the ``.ttf`` files into. Created
        with ``parents=True`` if missing.
    :type target_dir: ~pathlib.Path
    :return: Mapping ``{"regular": Path, "bold": Path}`` of the on-disk
        font files.
    :rtype: dict[str, ~pathlib.Path]
    :raises PatcherError: If a download or write fails.
    """
    log = LogMe("ensure_default_fonts")
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = get_font_paths(target_dir)
    if fonts_present(target_dir):
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
