"""Installomator label-fragment parser.

The single source of truth shared by the library's (deprecated)
``InstallomatorClient`` and the API's catalog ingest.

The parser is a small quote-aware *scanner* rather than a regex. Installomator
label values are shell expressions, and a non-greedy regex truncates them at
the first ``)`` or whitespace it meets, mangling pipelines like
``$(curl ... | sed -E 's/foo(bar)/x/')`` and parameter expansions like
``${rawVersion// build /.}``. The scanner reads each value to its true end by
tracking a stack of shell contexts (single/double quotes, backtick and
``$(...)`` command substitutions, ``(``/``{`` groups), so a ``$(`` opens a
fresh quoting context even inside double quotes and a value spanning multiple
physical lines is read as one unit.

A variable assigned more than once (the common resolve-then-transform or
arch-conditional pattern) is preserved as the ordered list of every
assignment. The projected scalar columns take the first assignment (the
resolving step / primary value); the full chain stays in the ``raw`` JSON
for consumers that need it.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_fragment"]


def _walk(text: str, *, stop_at_delim: bool) -> tuple[str, list[str], bool]:
    """
    Shared shell-context state machine used by every scan operation.

    Maintains a stack of nesting contexts so quoting behaves like bash: a
    ``$(...)`` command substitution opens a fresh quoting context even inside
    double quotes, so ``"$(curl "x")"`` reads as one value instead of closing
    the outer quote at the inner ``"``.

    Contexts: ``sq`` (single quote, fully literal), ``dq`` (double quote;
    backslash escapes and ``$(`` / backtick still active), ``bt`` (backtick
    command sub), ``cmd`` (``$(...)``), ``paren`` (a ``(`` or ``{`` group).

    :param stop_at_delim: When ``True`` (value scanning) stop at the first
        top-level whitespace, ``;``, or unmatched close bracket. When ``False``
        (openness / balance checks) consume the whole string.
    :returns: ``(captured_text, final_stack, saw_unmatched_close)``.
    """
    out: list[str] = []
    stack: list[str] = []
    saw_unmatched_close = False
    i, n = 0, len(text)

    while i < n:
        c = text[i]
        top = stack[-1] if stack else None

        if top == "sq":
            out.append(c)
            if c == "'":
                stack.pop()
            i += 1
            continue
        if top == "bt":
            out.append(c)
            if c == "`":
                stack.pop()
            i += 1
            continue
        if top == "dq":
            if c == "\\" and i + 1 < n:
                out.append(c + text[i + 1])
                i += 2
                continue
            if c == '"':
                out.append(c)
                stack.pop()
                i += 1
                continue
            if c == "$" and i + 1 < n and text[i + 1] == "(":
                out.append("$(")
                stack.append("cmd")
                i += 2
                continue
            if c == "`":
                out.append(c)
                stack.append("bt")
                i += 1
                continue
            out.append(c)
            i += 1
            continue

        # normal shell context: top is None, 'cmd', or 'paren'
        if c == "\\" and i + 1 < n:
            out.append(c + text[i + 1])
            i += 2
            continue
        if c == "'":
            out.append(c)
            stack.append("sq")
            i += 1
            continue
        if c == '"':
            out.append(c)
            stack.append("dq")
            i += 1
            continue
        if c == "`":
            out.append(c)
            stack.append("bt")
            i += 1
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            out.append("$(")
            stack.append("cmd")
            i += 2
            continue
        if c in "({":
            out.append(c)
            stack.append("paren")
            i += 1
            continue
        if c in ")}":
            if top in ("cmd", "paren"):
                out.append(c)
                stack.pop()
                i += 1
                continue
            saw_unmatched_close = True
            if stop_at_delim:
                break
            i += 1
            continue
        if not stack and (c.isspace() or c == ";"):
            if stop_at_delim:
                break
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1

    return "".join(out), stack, saw_unmatched_close


def _scan_value(text: str) -> str:
    """Read a single assignment value from the start of ``text``, intact."""
    return _walk(text, stop_at_delim=True)[0]


def _is_open(text: str) -> bool:
    """True if ``text`` ends inside an unclosed bracket or quote span."""
    return bool(_walk(text, stop_at_delim=False)[1])


def _strip_quotes(value: str) -> str:
    """Strip one layer of matched surrounding quotes, if present."""
    if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
        return value[1:-1]
    return value


def _logical_lines(fragment: str) -> list[str]:
    """
    Group physical lines into logical statements.

    A line whose brackets/quotes do not close keeps absorbing following lines
    until they do, so multi-line command substitutions and arrays survive
    intact. Full-line comments and blanks are skipped before a statement starts
    so a stray apostrophe in a comment (``it's``) can't look like an open quote
    and swallow the lines that follow.
    """
    out: list[str] = []
    buf = ""
    for raw_line in fragment.splitlines():
        if not buf:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
        candidate = f"{buf}\n{raw_line}" if buf else raw_line
        if _is_open(candidate):
            buf = candidate
        else:
            out.append(candidate)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _parse_array(inner: str) -> list[str]:
    """
    Split a bash array body into elements, honoring quotes and ``$(...)``.

    Naive whitespace splitting shreds elements that are themselves command
    substitutions (``versions=( $(curl ...) )``); scanning each element with
    the same value reader keeps them whole.
    """
    elements: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i].isspace():
            i += 1
            continue
        token = _scan_value(inner[i:])
        if not token:
            i += 1
            continue
        elements.append(_strip_quotes(token))
        i += len(token)
    return elements


def parse_fragment(fragment: str) -> dict[str, Any]:
    """
    Parse an Installomator label fragment into a dict of variable assignments.

    Recognized syntaxes:

    - ``key="quoted value"``: string values, surrounding quotes stripped.
    - ``key=$(shell expression)``: preserved verbatim as the literal expression.
    - ``key=(arr "values" here)``: bash arrays returned as Python lists.

    A key assigned exactly once maps to a scalar string (or a list, for a bash
    array). A key assigned more than once maps to the ordered list of every
    assignment, so the resolve step in a resolve-then-transform chain and the
    primary URL in an arch-conditional branch are never discarded. Consumers
    that need a single value should take the first element.

    Lines starting with ``#`` and blank lines are skipped. The opening
    ``<label>)`` header (including multi-name ``a|b|c)`` headers) and the
    trailing ``;;`` separator are stripped before parsing.
    """
    fragment = re.sub(r"^[\w|\\\s-]+\)\s*", "", fragment).strip()
    fragment = re.sub(r";;\s*$", "", fragment).strip()

    assignments: dict[str, list[Any]] = {}
    for line in _logical_lines(fragment):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^(\w+)=(.*)$", stripped, re.DOTALL)
        if not match:
            continue
        key, rest = match.group(1), match.group(2)
        value = _scan_value(rest)

        parsed: Any
        if value.startswith("(") and value.endswith(")"):
            parsed = _parse_array(value[1:-1])
        else:
            parsed = _strip_quotes(value)

        assignments.setdefault(key, []).append(parsed)

    return {key: (vals[0] if len(vals) == 1 else vals) for key, vals in assignments.items()}
