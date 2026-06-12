"""App-name normalization shared by the library matcher and the API catalog stitch."""

import re


def normalize_name(name: str | None) -> str:
    """
    Lowercase and strip all non-alphanumeric characters, for cross-variant name matching.

    App names appear in both whitespace-separated (``"Google Chrome"``) and
    concatenated (``"GoogleChrome"``) forms across sources; both normalize to
    ``"googlechrome"`` so either variant matches. Empty or ``None`` input returns
    ``""`` (callers guard against matching on empty keys).
    """
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())
