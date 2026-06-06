import asyncio
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..core.exceptions import APIResponseError, PatcherError
from ..core.logger import LogMe
from ..core.models.label import Label
from ..policy import INGEST_EXCLUDED_TEAM_IDS
from . import HTTPClient

# Installomator hosts a flat list of every label name in Labels.txt at the
# repo root. Parsing this file before fetching individual fragments lets us
# avoid the ~700-call directory-listing + mass-download fan-out that the
# previous implementation performed on first run.
_INSTALLOMATOR_RAW_BASE = (
    "https://raw.githubusercontent.com/Installomator/Installomator/refs/heads/main"
)
_LABELS_TXT_URL = f"{_INSTALLOMATOR_RAW_BASE}/Labels.txt"
_FRAGMENT_URL_TEMPLATE = f"{_INSTALLOMATOR_RAW_BASE}/fragments/labels/{{name}}.sh"


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

    Module-level so consumers outside :class:`InstallomatorClient` (notably
    Patcher API's ingestion) can call the same parser without instantiating
    the class. The original ``InstallomatorClient._parse`` delegates here.

    Uses a quote-aware scanner rather than a regex: Installomator values are
    shell expressions, and a non-greedy regex truncates them at the first ``)``
    or whitespace (mangling pipelines like ``$(curl ... | sed 's/foo(bar)/x/')``
    and expansions like ``${rawVersion// build /.}``). The scanner tracks a
    stack of shell contexts so values are read to their true end, even across
    multiple physical lines and inside nested quoting.

    Recognized syntaxes:

    - ``key="quoted value"``: string values, surrounding quotes stripped.
    - ``key=$(shell expression)``: preserved verbatim as the literal expression string.
    - ``key=(arr "values" here)``: bash arrays returned as Python lists.

    A key assigned more than once (resolve-then-transform, arch-conditional
    branches) maps to the ordered list of every assignment; consumers needing a
    single value take the first element. Lines starting with ``#`` and blank
    lines are skipped. The opening ``<label>)`` header (including multi-name
    ``a|b|c)`` headers) and trailing ``;;`` separator are stripped first.

    :param fragment: Raw ``.sh`` fragment content as fetched from the Installomator repo.
    :type fragment: str
    :return: Variable name → value (string for kv pairs, list for arrays or
        multi-assignment chains).
    :rtype: dict[str, Any]
    """
    fragment = re.sub(r"^[\w|\\\s-]+\)\s*", "", fragment).strip()  # Remove opening key(s)
    fragment = re.sub(r";;\s*$", "", fragment).strip()  # Remove trailing ;;

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


class InstallomatorClient:
    def __init__(self, concurrency: int = 5, api: HTTPClient | None = None):
        """
        Wrapper around the `Installomator <https://github.com/Installomator/Installomator>`_ project (the macOS automated-installer script set).

        This class provides methods for discovering, fetching, and matching Installomator labels to ``PatchTitle`` objects. Discovery uses the lightweight ``Labels.txt`` file at the Installomator repo root; individual ``.sh`` fragments are fetched lazily and only for matches.

        :param concurrency: Maximum concurrent requests for label fetches. Defaults to 5.
        :type concurrency: int
        :param api: HTTP client used for fetches against Installomator's GitHub.
            Defaults to a fresh :class:`~patcher.clients.HTTPClient`. No Jamf
            credentials required, so library callers can use
            ``InstallomatorClient()`` standalone to enumerate or fetch labels.
            When :meth:`match` is needed, pass a configured
            :class:`~patcher.clients.jamf.JamfClient` instead (it inherits
            from ``HTTPClient`` and adds the Jamf-specific
            :meth:`~patcher.clients.jamf.JamfClient.get_app_names` call that
            ``match()`` requires). :class:`PatcherClient` injects its
            shared ``JamfClient`` automatically.
        :type api: :class:`~patcher.clients.HTTPClient` | None
        """
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.api = api if api is not None else HTTPClient(max_concurrency=concurrency)

        # Session-scoped caches. `_available_names` holds the parsed Labels.txt
        # contents (a set of script names). `_labels_by_name` holds Label
        # objects keyed by script name as they are fetched.
        self._available_names: set[str] | None = None
        self._labels_by_name: dict[str, Label] = {}

    def _build_label_from_content(self, content: str, script_name: str) -> Label | None:
        """
        Parse a fragment's raw .sh content into a ``Label`` object.

        Returns ``None`` if the fragment's expected Team ID is in
        :data:`~patcher.policy.INGEST_EXCLUDED_TEAM_IDS` or if Pydantic validation fails.
        """
        fragment_dict = parse_fragment(content)

        # A key assigned more than once (resolve-then-transform, arch-conditional
        # branches) or as a bash array parses to a list. The Label model's scalar
        # fields take the first assignment (the resolving step / primary value),
        # matching the API-side projection.
        fragment_dict = {
            key: (value[0] if isinstance(value, list) and value else value)
            for key, value in fragment_dict.items()
        }

        expected_team_id = fragment_dict.get("expectedTeamID")
        if expected_team_id in INGEST_EXCLUDED_TEAM_IDS:
            self.log.warning(f"Skipping label {script_name} (ignored Team ID: {expected_team_id})")
            return None

        try:
            return Label.from_dict(fragment_dict, installomator_label=script_name)
        except ValidationError as e:
            self.log.warning(
                f"Skipping invalid Installomator label: {script_name} due to validation error: {e}"
            )
            return None

    async def list_available_labels(self) -> set[str]:
        """
        Return the set of every label name currently available in Installomator.

        Fetches and parses ``_LABELS_TXT_URL``. The result is cached on the instance for the session; subsequent calls do not re-fetch.

        :return: A set of label script names (e.g. ``{"googlechrome", "1password8", ...}``).
        :rtype: set[str]
        :raises PatcherError: If the labels file cannot be fetched.
        """
        if self._available_names is not None:
            return self._available_names

        self.log.debug(f"Fetching Installomator Labels.txt from {_LABELS_TXT_URL}")
        try:
            content = await self.api.fetch_text(_LABELS_TXT_URL)
        except APIResponseError as e:
            raise PatcherError("Unable to retrieve Installomator Labels.txt", error_msg=str(e))

        # Labels.txt is one label name per line. Strip whitespace, drop blanks
        # and comments (lines starting with '#'), normalize to lowercase to
        # match the rest of the matching pipeline.
        names = {
            line.strip().lower()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        self._available_names = names
        self.log.info(f"Discovered {len(names)} Installomator labels.")
        return names

    async def get_label(self, name: str) -> Label | None:
        """
        Fetch and parse a single Installomator label by script name.

        Lookup order:

        1. Instance cache (``self._labels_by_name``)
        2. On-disk cache (``~/Library/Application Support/Patcher/.labels/<name>.sh``)
        3. HTTP fetch from ``_FRAGMENT_URL_TEMPLATE``

        :param name: The Installomator script name (e.g. ``"googlechrome"``).
            Case-insensitive; normalized to lowercase before lookup.
        :type name: str
        :return: The constructed ``Label`` object, or ``None`` if the fragment
            cannot be fetched, is ignored by Team ID, or fails validation.
        :rtype: :class:`~patcher.core.models.label.Label` | None
        """
        key = name.lower()
        if key in self._labels_by_name:
            return self._labels_by_name[key]

        # On-disk cache
        cache_path = self.label_path / f"{key}.sh"
        if cache_path.exists():
            try:
                content = cache_path.read_text()
                label = self._build_label_from_content(content, key)
                if label is not None:
                    self._labels_by_name[key] = label
                return label
            except OSError as e:
                self.log.warning(
                    f"Could not read cached fragment {cache_path}; will refetch. Details: {e}"
                )

        # fetch_text raises APIResponseError on non-2xx (not_found=True on 404),
        # so we never parse error bodies as labels. Best-effort: log and return
        # None so one broken label doesn't kill the batch.
        url = _FRAGMENT_URL_TEMPLATE.format(name=key)
        self.log.debug(f"Fetching Installomator fragment from {url}")
        try:
            content = await self.api.fetch_text(url)
        except APIResponseError as e:
            self.log.warning(f"Failed to fetch Installomator fragment for '{name}': {e}")
            return None

        if not content:
            return None

        # Best-effort cache write; failure here doesn't prevent returning the label
        try:
            self.label_path.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(content)
        except OSError as e:
            self.log.warning(f"Could not write fragment cache to {cache_path}: {e}")

        label = self._build_label_from_content(content, key)
        if label is not None:
            self._labels_by_name[key] = label
        return label

    async def get_labels(self, names: Iterable[str] | None = None) -> list[Label]:
        """
        Fetch and parse multiple Installomator labels in parallel.

        :param names: Specific label script names to fetch. If ``None`` (the
            default), fetches **every** label listed in ``_LABELS_TXT_URL``,
            typically ~700 HTTP calls on first run and served from disk cache
            on subsequent runs. Prefer passing a concrete name list when you
            know what you need.
        :type names: Iterable[str] | None
        :return: List of successfully parsed ``Label`` objects. Labels that
            fail to fetch, hit an ignored Team ID, or fail validation are
            silently omitted (warnings are logged).
        :rtype: list[:class:`~patcher.core.models.label.Label`]
        """
        if names is None:
            names_iter = await self.list_available_labels()
        else:
            names_iter = {n.lower() for n in names}

        if not names_iter:
            return []

        tasks = [self.get_label(name) for name in names_iter]
        results = await asyncio.gather(*tasks)
        return [label for label in results if label is not None]
