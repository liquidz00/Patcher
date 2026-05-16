import asyncio
import fnmatch
import json
import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError
from rapidfuzz import fuzz, process

from ..client import HTTPClient
from ..client.jamf import JamfClient
from .exceptions import APIResponseError, PatcherError
from .logger import LogMe
from .models.label import Label
from .models.patch import PatchTitle

IGNORED_TEAMS = ["Frydendal", "Media", "LL3KBL2M3A"]  # "LL3KBL2M3A" - lcadvancedvpnclient

# Installomator hosts a flat list of every label name in Labels.txt at the
# repo root. Parsing this file before fetching individual fragments lets us
# avoid the ~700-call directory-listing + mass-download fan-out that the
# previous implementation performed on first run.
_INSTALLOMATOR_RAW_BASE = (
    "https://raw.githubusercontent.com/Installomator/Installomator/refs/heads/main"
)
_LABELS_TXT_URL = f"{_INSTALLOMATOR_RAW_BASE}/Labels.txt"
_FRAGMENT_URL_TEMPLATE = f"{_INSTALLOMATOR_RAW_BASE}/fragments/labels/{{name}}.sh"


def parse_fragment(fragment: str) -> dict[str, Any]:
    """
    Parse an Installomator label fragment into a dict of variable assignments.

    Module-level so consumers outside :class:`InstallomatorClient` (notably
    Patcher API's ingestion) can call the same parser without instantiating
    the class. The original ``InstallomatorClient._parse`` delegates here.

    Recognized syntaxes:

    - ``key="quoted value"``: string values, surrounding quotes stripped.
    - ``key=$(shell expression)``: preserved verbatim as the literal expression string.
    - ``key=(arr "values" here)``: bash arrays returned as Python lists.

    Lines starting with ``#`` and blank lines are skipped. The opening
    ``<label>)`` header and trailing ``;;`` separator are stripped before parsing.

    :param fragment: Raw ``.sh`` fragment content as fetched from the Installomator repo.
    :type fragment: str
    :return: Variable name → value (string for kv pairs, list for arrays).
    :rtype: dict[str, Any]
    """
    fragment = re.sub(r"^\w+\)\s*", "", fragment).strip()  # Remove opening key
    fragment = re.sub(r";;\s*$", "", fragment).strip()  # Remove trailing ;;

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


class InstallomatorClient:
    def __init__(self, concurrency: int = 5, api: HTTPClient | None = None):
        """
        Wrapper around the `Installomator <https://github.com/Installomator/Installomator>`_ project (the macOS automated-installer script set).

        This class provides methods for discovering, fetching, and matching Installomator labels to ``PatchTitle`` objects. Discovery uses the lightweight ``Labels.txt`` file at the Installomator repo root; individual ``.sh`` fragments are fetched lazily and only for matches.

        :param concurrency: Maximum concurrent requests for label fetches. Defaults to 5.
        :type concurrency: int
        :param api: HTTP client used for fetches against Installomator's GitHub.
            Defaults to a fresh :class:`~patcher.client.HTTPClient`. No Jamf
            credentials required, so library callers can use
            ``InstallomatorClient()`` standalone to enumerate or fetch labels.
            When :meth:`match` is needed, pass a configured
            :class:`~patcher.client.jamf.JamfClient` instead (it inherits
            from ``HTTPClient`` and adds the Jamf-specific
            :meth:`~patcher.client.jamf.JamfClient.get_app_names` call that
            ``match()`` requires). :class:`PatcherClient` injects its
            shared ``JamfClient`` automatically.
        :type api: :class:`~patcher.client.HTTPClient` | None
        """
        self.log = LogMe(self.__class__.__name__)
        self.label_path = Path.home() / "Library/Application Support/Patcher/.labels"
        self.api = api if api is not None else HTTPClient(max_concurrency=concurrency)
        self.threshold = 85
        self.review_file = Path.home() / "Library/Application Support/Patcher/unmatched_apps.json"

        # Session-scoped caches. `_available_names` holds the parsed Labels.txt
        # contents (a set of script names). `_labels_by_name` holds Label
        # objects keyed by script name as they are fetched.
        self._available_names: set[str] | None = None
        self._labels_by_name: dict[str, Label] = {}

    @staticmethod
    def _parse(fragment: str) -> dict[str, Any]:
        """Parses the passed fragment string and returns dictionary of formatted key-values."""
        return parse_fragment(fragment)

    def _build_label_from_content(self, content: str, script_name: str) -> Label | None:
        """
        Parse a fragment's raw .sh content into a ``Label`` object.

        Returns ``None`` if the fragment's expected Team ID is in
        :data:`IGNORED_TEAMS` or if Pydantic validation fails.
        """
        fragment_dict = self._parse(content)

        expected_team_id = fragment_dict.get("expectedTeamID")
        if expected_team_id in IGNORED_TEAMS:
            self.log.warning(f"Skipping label {script_name} (ignored Team ID: {expected_team_id})")
            return None

        try:
            return Label.from_dict(fragment_dict, installomatorLabel=script_name)
        except ValidationError as e:
            self.log.warning(
                f"Skipping invalid Installomator label: {script_name} due to validation error: {e}"
            )
            return None

    async def list_available_labels(self) -> set[str]:
        """
        Return the set of every label name currently available in Installomator.

        Fetches and parses :data:`_LABELS_TXT_URL`. The result is cached on the instance for the session; subsequent calls do not re-fetch.

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
        3. HTTP fetch from :data:`_FRAGMENT_URL_TEMPLATE`

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

        # HTTP fetch. `fetch_text` raises `APIResponseError` on non-2xx
        # (with `not_found=True` on 404) so we don't silently parse "404:
        # Not Found" bodies as labels. Treat any fetch failure as
        # best-effort: log and return None so a single broken label
        # doesn't kill the batch.
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
            default), fetches **every** label listed in :data:`_LABELS_TXT_URL`,
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

    @staticmethod
    def _normalize(app_name: str) -> str:
        """Normalizes app names to better match Installomator labels (e.g. nodejs)."""
        return app_name.lower().replace(" ", "").replace(".", "")

    def _match_directly(self, app_names: list[str], available: set[str]) -> list[str]:
        """Direct and normalized name matching against the available script-name set."""
        matched: list[str] = []
        for app_name in app_names:
            lower = app_name.lower()
            if lower in available and lower not in matched:
                matched.append(lower)
            normalized = self._normalize(app_name)
            if normalized in available and normalized not in matched:
                matched.append(normalized)
        return matched

    def _match_fuzzy(self, app_names: list[str], available: set[str]) -> list[str]:
        """Fuzzy match (rapidfuzz ratio) against the available script-name set."""
        matched: list[str] = []
        choices = list(available)
        for app_name in app_names:
            result = process.extractOne(app_name.lower(), choices, scorer=fuzz.ratio)  # type: ignore
            if result:
                best_match, score, _ = result
                if best_match and score >= self.threshold and best_match not in matched:
                    matched.append(best_match)
        return matched

    async def _second_pass(
        self,
        unmatched_apps: list[dict[str, Any]],
        available: set[str],
        patch_titles: list[PatchTitle],
    ) -> int:
        """Retry unmatched apps using normalized + fuzzy matching on the patch title itself."""
        matched_count = 0
        still_unmatched: list[dict[str, Any]] = []

        for entry in unmatched_apps:
            patch_name = entry["Patch"]
            normalized_patch = self._normalize(patch_name)
            patch_title = next((pt for pt in patch_titles if pt.title == patch_name), None)

            target_name: str | None = None
            if normalized_patch in available:
                target_name = normalized_patch
                self.log.debug(f"Second-pass normalized match for {patch_name} → {target_name}")
            else:
                result = process.extractOne(normalized_patch, list(available), scorer=fuzz.ratio)  # type: ignore
                if result:
                    best_match, score, _ = result
                    if best_match and score >= self.threshold:
                        target_name = best_match
                        self.log.debug(
                            f"Second-pass fuzzy match for {patch_name} → {target_name} (score {score})"
                        )

            if target_name and patch_title is not None:
                label = await self.get_label(target_name)
                if label is not None:
                    patch_title.install_label.append(label)
                    matched_count += 1
                    continue

            still_unmatched.append(entry)

        unmatched_apps[:] = still_unmatched
        return matched_count

    def _save_unmatched_apps(self, unmatched_apps: list[dict[str, Any]]) -> None:
        """Saves unmatched apps to a JSON file for later review."""
        self.review_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.review_file, "w") as file:
            json.dump(unmatched_apps, file, indent=4)  # type: ignore

    async def match(self, patch_titles: list[PatchTitle]) -> None:
        """
        Match Jamf patch titles to Installomator labels.

        Flow:

        1. Fetch the set of available label script names via :meth:`list_available_labels` (one HTTP call).
        2. Pull each patch title's associated app names via :meth:`~patcher.client.jamf.JamfClient.get_app_names`.
        3. Match each title's app names against the available script names (direct, then normalized, then fuzzy).
        4. Fetch the matched label fragments in parallel via :meth:`get_labels` and attach them to ``PatchTitle.install_label``.
        5. Run a second-pass attempt on still-unmatched titles, keyed on the patch title text itself.
        6. Persist any remaining unmatched apps to ``unmatched_apps.json`` for manual review.

        :param patch_titles: The list of ``PatchTitle`` objects to match. Each
            successfully matched title has its ``install_label`` attribute
            extended in place.
        :type patch_titles: list[:class:`~patcher.core.models.patch.PatchTitle`]
        :raises PatcherError: If this :class:`InstallomatorClient` was not
            constructed with a :class:`~patcher.client.jamf.JamfClient` (the
            default ``HTTPClient`` cannot call Jamf's ``get_app_names``
            endpoint). Pass ``api=<JamfClient>`` at construction, or use
            :class:`~patcher.core.patcher_client.PatcherClient` which wires
            this automatically.
        """
        if not isinstance(self.api, JamfClient):
            raise PatcherError(
                "InstallomatorClient.match() requires a configured JamfClient. "
                "Construct InstallomatorClient(api=<JamfClient>) or use PatcherClient.",
            )

        self.log.debug("Starting label-patch title matching process.")

        IGNORED_TITLES = [  # noqa: N806
            "Apple macOS *",
            "Oracle Java SE *",
            "Eclipse Temurin *",
            "Apple Safari",
            "Apple Xcode",
            "Microsoft Visual Studio",  # Support deprecated
        ]

        try:
            software_titles = await self.api.get_app_names(patch_titles=patch_titles)
        except APIResponseError as e:
            if getattr(e, "not_found", False):
                return  # Exit early, do not stop process
            raise  # Non-404 errors get re-raised

        available = await self.list_available_labels()

        # Compute matches per patch title, gathering all unique script names we'll need
        per_title_matches: dict[str, list[str]] = {}
        unmatched_apps: list[dict[str, Any]] = []

        for patch_title in patch_titles:
            if any(fnmatch.fnmatch(patch_title.title, pattern) for pattern in IGNORED_TITLES):
                self.log.info(f"Ignoring {patch_title.title}")
                continue

            app_name_entry = next(
                (entry for entry in software_titles if entry["Patch"] == patch_title.title), None
            )
            app_names = app_name_entry["App Names"] if app_name_entry else []

            if not app_names:
                self.log.warning(f"Skipping {patch_title.title} - No app names found.")
                unmatched_apps.append({"Patch": patch_title.title, "App Names": []})
                continue

            matched_names = self._match_directly(app_names, available) or self._match_fuzzy(
                app_names, available
            )

            if matched_names:
                per_title_matches[patch_title.title] = matched_names
            else:
                unmatched_apps.append({"Patch": patch_title.title, "App Names": app_names})

        # Single batched fetch for every distinct matched script name
        all_matched_names: set[str] = {n for names in per_title_matches.values() for n in names}
        if all_matched_names:
            await self.get_labels(all_matched_names)

        matched_count = 0
        for patch_title in patch_titles:
            names = per_title_matches.get(patch_title.title)
            if not names:
                continue
            labels_for_title = [self._labels_by_name[n] for n in names if n in self._labels_by_name]
            if labels_for_title:
                patch_title.install_label.extend(labels_for_title)
                matched_count += 1

        # Second pass on unmatched: try normalized patch title + fuzzy
        matched_count += await self._second_pass(unmatched_apps, available, patch_titles)

        self._save_unmatched_apps(unmatched_apps)

        self.log.info(
            f"Matching process finished. {matched_count} PatchTitle objects were updated."
        )
        if unmatched_apps:
            self.log.warning(
                f"{len(unmatched_apps)} PatchTitle objects had no matches. Review: {self.review_file}"
            )


# Shell expression resolution: the "pyinstallomator" subset.
#
# Installomator labels frequently declare values via shell pipelines, e.g.::
#
#     appNewVersion=$(curl -fsIL "https://download.mozilla.org/?product=firefox-latest" \
#       | grep -i ^location | cut -d "/" -f7)
#
# The Patcher API ingestion pipeline needs the *resolved* value (e.g. "121.0")
# rather than the raw shell expression. The functions below parse such
# expressions and re-implement each pipeline stage in Python (no subprocess,
# no shell evaluation, no sandboxing concerns), so resolution can run safely
# against ~700 community-authored label snippets without executing any of them.
#
# Supported vocabulary:
#   - curl (flags: -f, -s, -I, -L; HEAD or GET; redirect-chain headers)
#   - grep (flags: -i, -o, -v, -E)
#   - head (-n N or -N)
#   - tail (-n N or -N)
#   - cut  (-d DELIM, -f SPEC; spec supports N, N1,N2, N1-N2)
#
# Patterns outside this vocabulary return a ResolveResult with
# method="unsupported" so the catalog can track where to extend next.


_SHELL_EXPR_PATTERN = re.compile(r"^\$\((.*)\)\s*$", re.DOTALL)


@dataclass
class ResolveResult:
    """
    Outcome of resolving a single expression.

    :ivar value: Resolved scalar value, or ``None`` if resolution failed.
    :vartype value: str | None
    :ivar error: Human-readable failure description, or ``None`` on success.
    :vartype error: str | None
    :ivar method: ``"literal"`` (input wasn't a shell expression),
        ``"pipeline"`` (resolved by running the pipeline),
        ``"unsupported"`` (some command in the pipeline isn't yet handled),
        or ``"error"`` (resolution attempted but a runtime error occurred).
    :vartype method: str
    """

    value: str | None
    error: str | None
    method: str


class UnsupportedOperation(Exception):
    """Raised when a pipeline contains a command pyinstallomator doesn't yet handle."""


def resolve(
    expression: str | None,
    *,
    http_client: httpx.Client | None = None,
) -> ResolveResult:
    """
    Resolve a label variable's value, evaluating shell-style pipelines in Python.

    :param expression: The label variable value as parsed from the ``.sh`` fragment.
        Plain strings (``"121.0"``) pass through as literals; values shaped
        ``$(cmd | cmd | ...)`` are parsed and evaluated.
    :type expression: str | None
    :param http_client: Optional pre-configured ``httpx.Client``. If omitted,
        a fresh client with a 30-second timeout is created and disposed per
        ``curl`` invocation. Tests inject a ``MockTransport``-backed client
        to avoid hitting real URLs.
    :type http_client: httpx.Client | None
    :return: The :class:`ResolveResult`.
    :rtype: :class:`ResolveResult`
    """
    if expression is None:
        return ResolveResult(value=None, error=None, method="literal")

    match = _SHELL_EXPR_PATTERN.match(expression.strip())
    if not match:
        return ResolveResult(value=expression, error=None, method="literal")

    inner = match.group(1).strip()
    stages = _split_pipeline(inner)

    try:
        result_lines = _execute_pipeline(stages, http_client=http_client)
    except UnsupportedOperation as exc:
        return ResolveResult(value=None, error=str(exc), method="unsupported")
    except Exception as exc:
        return ResolveResult(value=None, error=str(exc), method="error")

    if not result_lines:
        return ResolveResult(value=None, error="Pipeline produced empty output", method="pipeline")

    # Most expressions reduce to a single value via head/cut/grep -o, so this
    # is usually just one line, but join multi-line output on \n if not.
    return ResolveResult(value="\n".join(result_lines), error=None, method="pipeline")


def _split_pipeline(expr: str) -> list[str]:
    """Split a shell pipeline on ``|`` while respecting single/double-quoted regions."""
    stages: list[str] = []
    current: list[str] = []
    quote: str | None = None

    for char in expr:
        if char in ("'", '"') and quote is None:
            quote = char
            current.append(char)
        elif char == quote:
            quote = None
            current.append(char)
        elif char == "|" and quote is None:
            stages.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        stages.append("".join(current).strip())
    return stages


def _tokenize(stage: str) -> list[str]:
    """Shell-style tokenization (handles quoted args)."""
    return shlex.split(stage)


def _execute_pipeline(
    stages: list[str],
    *,
    http_client: httpx.Client | None,
) -> list[str]:
    """Walk pipeline stages left-to-right, threading list-of-lines between them."""
    output: list[str] = []
    for index, stage in enumerate(stages):
        tokens = _tokenize(stage)
        if not tokens:
            raise UnsupportedOperation(f"Empty pipeline stage at position {index}")
        cmd, args = tokens[0], tokens[1:]
        if index == 0:
            # First stage is the source; must produce output (curl).
            output = _exec_source(cmd, args, http_client=http_client)
        else:
            output = _exec_filter(cmd, args, output)
    return output


def _exec_source(cmd: str, args: list[str], *, http_client: httpx.Client | None) -> list[str]:
    if cmd == "curl":
        return _exec_curl(args, http_client=http_client)
    raise UnsupportedOperation(f"Unsupported source command: {cmd!r}")


def _exec_filter(cmd: str, args: list[str], input_lines: list[str]) -> list[str]:
    if cmd == "grep":
        return _exec_grep(args, input_lines)
    if cmd == "head":
        return _exec_head(args, input_lines)
    if cmd == "tail":
        return _exec_tail(args, input_lines)
    if cmd == "cut":
        return _exec_cut(args, input_lines)
    raise UnsupportedOperation(f"Unsupported filter command: {cmd!r}")


def _parse_short_flags(arg: str) -> str:
    """``-fsIL`` → ``"fsIL"``. ``-f`` → ``"f"``. Non-flag → ``""``."""
    if arg.startswith("-") and not arg.startswith("--"):
        return arg[1:]
    return ""


def _exec_curl(args: list[str], *, http_client: httpx.Client | None) -> list[str]:
    """
    Execute a ``curl`` invocation. Returns lines of output (body lines for GET,
    header lines for HEAD/redirect-chain).
    """
    fail_silent = False
    headers_only = False
    follow_redirects = False
    url: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        flags = _parse_short_flags(arg)
        if flags:
            for f in flags:
                if f == "f":
                    fail_silent = True
                elif f == "s":
                    pass  # we're always silent
                elif f == "I":
                    headers_only = True
                elif f == "L":
                    follow_redirects = True
        elif not arg.startswith("-"):
            url = arg
        i += 1

    if not url:
        raise UnsupportedOperation("curl requires a URL")

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        if headers_only and follow_redirects:
            return _curl_redirect_chain_headers(client, url, fail_silent=fail_silent)
        if headers_only:
            return _curl_headers(client, url, fail_silent=fail_silent)
        return _curl_body(client, url, follow_redirects=follow_redirects, fail_silent=fail_silent)
    finally:
        if owns_client:
            client.close()


def _curl_redirect_chain_headers(
    client: httpx.Client,
    url: str,
    *,
    fail_silent: bool,
) -> list[str]:
    """``curl -IL``: every redirect hop's status line + headers, in order."""
    lines: list[str] = []
    current = url
    for _ in range(10):  # max 10 hops
        try:
            response = client.head(current, follow_redirects=False)
        except httpx.HTTPError:
            if fail_silent:
                return lines
            raise
        lines.append(
            f"HTTP/{response.http_version} {response.status_code} {response.reason_phrase}"
        )
        for key, value in response.headers.items():
            lines.append(f"{key}: {value}")
        lines.append("")  # blank between header blocks
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if location:
                current = str(httpx.URL(current).join(location))
                continue
        break
    return lines


def _curl_headers(client: httpx.Client, url: str, *, fail_silent: bool) -> list[str]:
    """``curl -I``: status line + headers from the single response (no follow)."""
    try:
        response = client.head(url, follow_redirects=False)
    except httpx.HTTPError:
        if fail_silent:
            return []
        raise
    if fail_silent and response.is_error:
        return []
    lines = [f"HTTP/{response.http_version} {response.status_code} {response.reason_phrase}"]
    lines.extend(f"{key}: {value}" for key, value in response.headers.items())
    return lines


def _curl_body(
    client: httpx.Client, url: str, *, follow_redirects: bool, fail_silent: bool
) -> list[str]:
    """``curl`` (no ``-I``): response body, split into lines."""
    try:
        response = client.get(url, follow_redirects=follow_redirects)
    except httpx.HTTPError:
        if fail_silent:
            return []
        raise
    if fail_silent and response.is_error:
        return []
    return response.text.splitlines()


def _exec_grep(args: list[str], input_lines: list[str]) -> list[str]:
    """Filter ``input_lines`` by ``pattern``. Supports ``-i``, ``-o``, ``-v``, ``-E``."""
    case_insensitive = False
    only_matching = False
    invert = False
    pattern: str | None = None

    for arg in args:
        flags = _parse_short_flags(arg)
        if flags:
            for f in flags:
                if f == "i":
                    case_insensitive = True
                elif f == "o":
                    only_matching = True
                elif f == "v":
                    invert = True
                elif f == "E":
                    pass  # extended regex is our default
        elif pattern is None:
            pattern = arg

    if pattern is None:
        raise UnsupportedOperation("grep requires a pattern")

    regex = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
    out: list[str] = []
    for line in input_lines:
        match = regex.search(line)
        if invert:
            if not match:
                out.append(line)
        elif match:
            out.append(match.group(0) if only_matching else line)
    return out


def _exec_head(args: list[str], input_lines: list[str]) -> list[str]:
    """First ``n`` lines (default ``10``). Supports ``-n N`` and ``-N``."""
    n = _parse_count(args, default=10)
    return input_lines[:n]


def _exec_tail(args: list[str], input_lines: list[str]) -> list[str]:
    """Last ``n`` lines (default ``10``). Supports ``-n N`` and ``-N``."""
    n = _parse_count(args, default=10)
    return input_lines[-n:] if n > 0 else []


def _parse_count(args: list[str], *, default: int) -> int:
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-n" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
        elif arg.startswith("-") and arg[1:].isdigit():
            return int(arg[1:])
        i += 1
    return default


def _exec_cut(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Field extraction. Supports ``-d DELIM`` and ``-f N|N1,N2|N1-N2`` (1-indexed).
    Both separated (``-f 5``) and joined (``-f5``) flag-argument forms are
    accepted, since real Installomator labels use both.
    """
    delimiter = "\t"
    fields: list[int] = [1]

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-d" and i + 1 < len(args):
            delimiter = args[i + 1]
            i += 2
            continue
        if arg.startswith("-d") and len(arg) > 2:
            delimiter = arg[2:]
            i += 1
            continue
        if arg == "-f" and i + 1 < len(args):
            fields = _parse_field_spec(args[i + 1])
            i += 2
            continue
        if arg.startswith("-f") and len(arg) > 2:
            fields = _parse_field_spec(arg[2:])
            i += 1
            continue
        i += 1

    out: list[str] = []
    for line in input_lines:
        parts = line.split(delimiter)
        selected: list[str] = []
        for f in fields:
            if 1 <= f <= len(parts):
                selected.append(parts[f - 1])
        out.append(delimiter.join(selected))
    return out


def _parse_field_spec(spec: str) -> list[int]:
    """Parse ``cut -f`` spec: ``'1'`` → ``[1]``, ``'1,3'`` → ``[1, 3]``, ``'2-5'`` → ``[2,3,4,5]``."""
    fields: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            fields.extend(range(int(start_str), int(end_str) + 1))
        else:
            fields.append(int(part))
    return fields
