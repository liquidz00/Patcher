"""Installomator label-fragment parser for ingest.

Local copy of :func:`patcher.clients.installomator.parse_fragment` to sever
the api-workspace's only ``from patcher.*`` import. The function is pure
regex with no transitive dependencies, so the duplication cost is low and
the workspaces gain independent release cadence.

If parsing behavior changes in either copy, update both intentionally.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_fragment"]


def parse_fragment(fragment: str) -> dict[str, Any]:
    """
    Parse an Installomator label fragment into a dict of variable assignments.

    Recognized syntaxes:

    - ``key="quoted value"``: string values, surrounding quotes stripped.
    - ``key=$(shell expression)``: preserved verbatim as the literal expression string.
    - ``key=(arr "values" here)``: bash arrays returned as Python lists.

    Lines starting with ``#`` and blank lines are skipped. The opening
    ``<label>)`` header and trailing ``;;`` separator are stripped before parsing.
    """
    fragment = re.sub(r"^\w+\)\s*", "", fragment).strip()
    fragment = re.sub(r";;\s*$", "", fragment).strip()

    data: dict[str, Any] = {}
    lines = fragment.splitlines()

    kv_pattern = re.compile(r'^(\w+)=(".*?"|\$\(.*?\)|\S+)')
    array_pattern = re.compile(r"^(\w+)=\((.*?)\)$")

    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue

        array_match = array_pattern.match(line)
        if array_match:
            key, array_values = array_match.groups()
            pairs = re.findall(r'"(.*?)"|(\S+)', array_values)
            data[key] = [val[0] or val[1] for val in pairs]
            continue

        kv_match = kv_pattern.match(line)
        if kv_match:
            key, value = kv_match.groups()
            value = value.strip('"')
            data[key] = value
            continue

    return data
