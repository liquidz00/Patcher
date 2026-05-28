"""
Shell expression resolution: the "pyinstallomator" subset.

Installomator labels frequently declare values via shell pipelines, e.g.::

    appNewVersion=$(curl -fsIL "https://download.mozilla.org/?product=firefox-latest" \\
      | grep -i ^location | cut -d "/" -f7)

The Patcher API ingestion pipeline needs the *resolved* value (e.g. "121.0")
rather than the raw shell expression. :class:`PipelineResolver` parses such
expressions and evaluates each stage in Python — no subprocess, no shell
evaluation — so resolution can run safely against ~700 community-authored
label snippets without executing any of them.

This module owns pipeline orchestration and the *source* commands (``curl``,
``echo``, ``versionFromGit``, ``downloadURLFromGit``, ``getJSONValue``). The
*filter* stages (``grep``/``sed``/``awk``/``cut``/``tr``/``sort``/``uniq``/
``xpath``) live in :mod:`patcher_api.installomator._filters` and are dispatched
via ``apply_filter``.

Patterns outside the supported vocabulary raise :class:`UnsupportedOperation`.
Callers can opt into :func:`_subprocess_fallback` (handing the pipeline to
``bash``) by passing ``allow_subprocess_fallback=True``.

Historically lived under ``patcher.clients.installomator``. Moved here because
resolution is a Patcher-API ingest concern, not a ``patcher`` package concern —
the package consumes resolved values via the API rather than running pipelines.
"""

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass

import httpx

from patcher_api.installomator._filters import (
    UnsupportedOperation,
    _parse_short_flags,
    apply_filter,
)

_SHELL_EXPR_PATTERN = re.compile(r"^\$\((.*)\)\s*$", re.DOTALL)
_MAX_URL_LENGTH = 2000
# A version string is short; anything longer is a page/dump the pipeline failed to filter.
_MAX_VERSION_LENGTH = 60
# echo-argument references: a $(...) command sub, a ${...} brace ref, or a bare $var.
_EXPANSION_PATTERN = re.compile(
    r"\$\((?P<cmd>.*?)\)|\$\{(?P<brace>[^}]*)\}|\$(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)"
)
# A ${...} body that is *just* a variable name (no parameter-expansion ops).
_PLAIN_VAR = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_BASE = "https://github.com"
_SUBPROCESS_FALLBACK_TIMEOUT_SECONDS = 30.0
_SUBPROCESS_FALLBACK_PATH = "/usr/bin:/bin"


@dataclass
class Resolved:
    """A pipeline (or literal) produced a final, usable value. Caller stores it."""

    value: str


@dataclass
class Unresolvable:
    """
    We couldn't get a value at all. Pipeline contained an unsupported command,
    failed parsing, networked errored, or produced empty output. Caller nulls
    the column.
    """

    reason: str


@dataclass
class InvalidOutput:
    """
    We got a value, but it failed sanity checks (URL validator, etc). Caller
    nulls the column AND keeps the raw value for review. Distinct from
    :class:`Unresolvable` so callers can log "we got *something*, but rejected
    it" vs "we got nothing."
    """

    raw: str
    reason: str


ResolveOutcome = Resolved | Unresolvable | InvalidOutput


class PipelineResolver:
    """
    Evaluate an Installomator label's shell-expression value into a concrete
    string, in Python (no subprocess by default).

    Holds the state that threads through pipeline execution — the ``httpx``
    client reused across ``curl`` stages, the opt-in subprocess-fallback
    toggle, and the parsed-label context — so a caller resolving many labels
    constructs one resolver and reuses it across the batch. The stateless
    filter stages live in :mod:`._filters`; this class is the stateful
    execution core (orchestration + source commands).

    :param http_client: Optional pre-configured ``httpx.Client``. If omitted, a
        fresh client with a 30-second timeout is created and disposed per
        ``curl`` invocation. Tests inject a ``MockTransport``-backed client to
        avoid hitting real URLs.
    :type http_client: httpx.Client | None
    :param allow_subprocess_fallback: When ``True``, pipelines that raise
        :class:`UnsupportedOperation` during native dispatch fall through to
        :func:`_subprocess_fallback`. Off by default because the fallback
        invokes ``bash`` on a public-repo string, a real (accepted)
        shell-injection surface. Callers that pin the Installomator commit and
        trust the pipeline-string corpus can opt in.
    :type allow_subprocess_fallback: bool
    :param context: Parsed label dict, so source commands can read sibling
        variables (``downloadURLFromGit`` reads ``type``/``archiveName``;
        ``echo "${updateFeed}"`` resolves the prior assignment).
    :type context: dict | None
    """

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        *,
        allow_subprocess_fallback: bool = False,
        context: dict | None = None,
    ) -> None:
        self._http_client = http_client
        self._allow_subprocess_fallback = allow_subprocess_fallback
        self._context = context or {}
        # Names mid-resolution, to break cycles when one variable references another.
        self._var_stack: set[str] = set()

    def _execute_pipeline(self, stages: list[str]) -> list[str]:
        """Walk pipeline stages left-to-right, threading list-of-lines between them."""
        output: list[str] = []
        for index, stage in enumerate(stages):
            tokens = _tokenize(stage)
            if not tokens:
                raise UnsupportedOperation(f"Empty pipeline stage at position {index}")
            cmd, args = tokens[0], tokens[1:]
            if index == 0:
                # First stage is the source; must produce output (curl/echo/git/json).
                output = self._exec_source(cmd, args)
            else:
                output = apply_filter(cmd, args, output)
        return output

    def _exec_source(self, cmd: str, args: list[str]) -> list[str]:
        if cmd == "curl":
            return self._exec_curl(args)
        if cmd == "echo":
            return self._exec_echo(args)
        if cmd == "versionFromGit":
            if len(args) < 2:
                raise UnsupportedOperation("versionFromGit requires user and repo")
            return self._version_from_git(args[0], args[1])
        if cmd == "downloadURLFromGit":
            if len(args) < 2:
                raise UnsupportedOperation("downloadURLFromGit requires user and repo")
            return self._download_url_from_git(args[0], args[1])
        if cmd == "getJSONValue":
            if len(args) < 2:
                raise UnsupportedOperation("getJSONValue requires a JSON source and a key")
            return self._get_json_value(args[0], args[1])
        raise UnsupportedOperation(f"Unsupported source command: {cmd!r}")

    def _exec_curl(self, args: list[str]) -> list[str]:
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

        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=30.0)
        try:
            if headers_only and follow_redirects:
                return _curl_redirect_chain_headers(client, url, fail_silent=fail_silent)
            if headers_only:
                return _curl_headers(client, url, fail_silent=fail_silent)
            return _curl_body(
                client, url, follow_redirects=follow_redirects, fail_silent=fail_silent
            )
        finally:
            if owns_client:
                client.close()

    def _exec_echo(self, args: list[str]) -> list[str]:
        """
        ``echo`` as a pipeline source, with variable + ``$(...)`` expansion.

        Labels frequently fetch a feed into one variable and parse it on a
        later line: ``updateFeed=$(curl ...)`` then
        ``downloadURL=$(echo "${updateFeed}" | xpath ...)``; likewise
        ``appNewVersion=$(echo "${downloadURL}" | sed ...)`` derives a version
        from the resolved download URL. We resolve ``${var}`` / ``$var`` by
        looking the name up in the parsed-label context and recursively
        resolving *its* expression, then echo the expanded text on into the
        pipeline. Bails (→ ``Unresolvable``) on a missing/unresolvable variable
        or a ``${var//…}`` parameter-expansion we don't evaluate.
        """
        expanded = self._expand(" ".join(args))
        if expanded is None:
            raise UnsupportedOperation("echo: unresolvable variable or unsupported expansion")
        return expanded.splitlines()

    def _resolve_var(self, name: str) -> str | None:
        """Resolve ``name`` against the label context, recursively, cycle-guarded."""
        if name in self._var_stack:
            return None  # cycle: var references itself (in)directly
        raw = _first(self._context.get(name))
        if raw is None:
            return None
        self._var_stack.add(name)
        try:
            outcome = self.resolve(raw)
        finally:
            self._var_stack.discard(name)
        return outcome.value if isinstance(outcome, Resolved) else None

    def _expand(self, text: str) -> str | None:
        """
        Expand ``$(...)``, ``${var}``, and ``$var`` references in ``text``.

        Returns ``None`` if any reference can't be resolved, or if a ``${...}``
        carries a parameter-expansion operator (``//``, ``%``, ``:``, …) we
        don't implement — so the caller treats the whole echo as unresolvable
        rather than emitting a half-expanded string.
        """
        out: list[str] = []
        last = 0
        for m in _EXPANSION_PATTERN.finditer(text):
            out.append(text[last : m.start()])
            if m.group("cmd") is not None:
                outcome = self.resolve(f"$({m.group('cmd')})")
                if not isinstance(outcome, Resolved):
                    return None
                out.append(outcome.value)
            else:
                name = m.group("brace") if m.group("brace") is not None else m.group("var")
                if not _PLAIN_VAR.fullmatch(name):
                    return None  # e.g. ${var//x/y}, ${var%suffix} — not supported
                value = self._resolve_var(name)
                if value is None:
                    return None
                out.append(value)
            last = m.end()
        out.append(text[last:])
        return "".join(out)

    def _version_from_git(self, user: str, repo: str) -> list[str]:
        """
        Latest release version for a GitHub repo, via the unauthenticated
        ``github.com/.../releases/latest`` redirect — no API token, no rate
        limit. Mirrors Installomator's ``versionFromGit``: follow the redirect
        to ``/releases/tag/<tag>`` and strip the tag to digits and dots.
        """
        owns = self._http_client is None
        client = self._http_client or httpx.Client(timeout=30.0)
        try:
            resp = client.head(
                f"{_GITHUB_BASE}/{user}/{repo}/releases/latest", follow_redirects=True
            )
        finally:
            if owns:
                client.close()
        tag = resp.url.path.rsplit("/tag/", 1)[-1] if "/tag/" in resp.url.path else ""
        version = re.sub(r"[^0-9.]", "", tag)
        return [version] if version else []

    def _download_url_from_git(self, user: str, repo: str) -> list[str]:
        """
        Latest release download URL for a GitHub repo, via the releases API.

        Picks the asset whose ``browser_download_url`` matches the label's
        ``archiveName`` (if set) or otherwise its ``type`` extension
        (``pkgInDmg`` → ``dmg``, ``pkgInZip`` → ``zip``). Authenticated when
        ``PATCHER_API_GITHUB_TOKEN`` is set (5000/hr vs 60/hr).
        """
        headers = {"Accept": "application/vnd.github+json"}
        token = _github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        owns = self._http_client is None
        client = self._http_client or httpx.Client(timeout=30.0)
        try:
            resp = client.get(
                f"{_GITHUB_API_BASE}/repos/{user}/{repo}/releases/latest",
                headers=headers,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                client.close()

        assets = data.get("assets") or []
        archive_name = _first(self._context.get("archiveName"))
        label_type = _first(self._context.get("type"))
        filetype = {"pkgInDmg": "dmg", "pkgInZip": "zip"}.get(label_type, label_type)

        for asset in assets:
            url = asset.get("browser_download_url", "")
            if archive_name and not archive_name.startswith("$"):
                if archive_name in url:
                    return [url]
            elif filetype and url.endswith(f".{filetype}"):
                return [url]
        return []

    def _get_json_value(self, source: str, key: str) -> list[str]:
        """
        Installomator's ``getJSONValue "<json>" "<key.path>"``.

        The first argument is almost always a nested ``$(curl ...)`` that
        fetches the JSON, so resolve it recursively (sharing this resolver's
        client + context) to get the document, then walk the dot/bracket key
        path with stdlib ``json``. A scalar is returned as-is; an object/array
        is re-serialized (mirroring the JXA helper's ``JSON.stringify`` branch).
        Returns ``[]`` (→ ``Unresolvable``) if the source can't be resolved,
        isn't valid JSON, or the key path doesn't exist — including key paths
        that reference shell variables (``[$count]``) we can't evaluate.
        """
        outcome = self.resolve(source)
        if not isinstance(outcome, Resolved):
            return []
        try:
            data = json.loads(outcome.value)
        except (json.JSONDecodeError, ValueError):
            return []
        value = _navigate_json(data, key)
        if value is None:
            return []
        if isinstance(value, dict | list):
            return [json.dumps(value)]
        return [str(value)]

    def resolve(
        self, expression: str | None, *, is_url: bool = False, is_version: bool = False
    ) -> ResolveOutcome:
        """
        Resolve a label variable's value, evaluating shell-style pipelines in Python.

        :param expression: The label variable value as parsed from the ``.sh``
            fragment. Plain strings (``"121.0"``) pass through as literals;
            values shaped ``$(cmd | cmd | ...)`` are parsed and evaluated.
        :type expression: str | None
        :param is_url: When ``True``, the resolved value is run through
            :func:`looks_like_clean_http_url` before returning. Failures land as
            :class:`InvalidOutput` so callers see "got something, rejected it"
            rather than "no value." Pass for fields whose projected column gets
            serialized as Pydantic ``HttpUrl``.
        :type is_url: bool
        :param is_version: When ``True``, the resolved value is run through
            :func:`looks_like_clean_version`. A pipeline that succeeds at the
            shell level but captures an HTML page, a header dump, or an
            un-filtered multi-line blob is rejected as :class:`InvalidOutput`
            rather than stored as a bogus version. Pass for ``appNewVersion``.
        :type is_version: bool
        :return: A :class:`Resolved`, :class:`Unresolvable`, or :class:`InvalidOutput`.
        :rtype: :class:`ResolveOutcome`
        """
        if expression is None:
            return Unresolvable(reason="expression is None")

        match = _SHELL_EXPR_PATTERN.match(expression.strip())
        if not match:
            # Literal value, no pipeline evaluation.
            return self._validated(expression, is_url=is_url, is_version=is_version, literal=True)

        inner = match.group(1).strip()
        stages = _split_pipeline(inner)

        try:
            result_lines = self._execute_pipeline(stages)
        except UnsupportedOperation as exc:
            if self._allow_subprocess_fallback:
                try:
                    result_lines = _subprocess_fallback(stages)
                except UnsupportedOperation as fallback_exc:
                    return Unresolvable(reason=f"subprocess fallback failed: {fallback_exc}")
            else:
                return Unresolvable(reason=f"unsupported command in pipeline: {exc}")
        except Exception as exc:
            return Unresolvable(reason=f"pipeline execution error: {exc}")

        if not result_lines:
            return Unresolvable(reason="pipeline produced empty output")

        value = "\n".join(result_lines)
        return self._validated(value, is_url=is_url, is_version=is_version, literal=False)

    @staticmethod
    def _validated(value: str, *, is_url: bool, is_version: bool, literal: bool) -> ResolveOutcome:
        """Apply the per-field sanity check, returning :class:`InvalidOutput` on failure."""
        if is_url and not looks_like_clean_http_url(value):
            reason = "literal but not a clean http(s) URL" if literal else "failed URL sanity check"
            return InvalidOutput(raw=value, reason=reason)
        if is_version and not looks_like_clean_version(value):
            reason = "literal but not a clean version" if literal else "failed version sanity check"
            return InvalidOutput(raw=value, reason=reason)
        return Resolved(value=value)


def _github_token() -> str | None:
    """GitHub token for authenticated API calls (5000/hr vs 60/hr unauth)."""
    return os.environ.get("PATCHER_API_GITHUB_TOKEN") or None


def _first(value: object) -> str | None:
    """First element of a multi-assignment chain / array, coerced to str."""
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) else None


def _navigate_json(data: object, key: str) -> object | None:
    """
    Walk a dot/bracket JSON key path (``getJSONValue``'s second argument).

    Handles ``computer.MacOS.releases[0].url``, ``[0].version``, and
    ``Automatic.fileURL``: numeric brackets index lists, quoted brackets
    (``["key"]``) and bare segments index dicts. Returns ``None`` if a step is
    missing or the path references something we can't evaluate — notably a
    shell variable like ``[$count]`` — so the caller nulls the column.
    """
    current = data
    for bracket, name in re.findall(r"\[([^\]]+)\]|([^.\[\]]+)", key):
        if bracket:
            token = bracket.strip()
            if token.isdigit():
                if not isinstance(current, list) or int(token) >= len(current):
                    return None
                current = current[int(token)]
            elif len(token) >= 2 and token[0] in "\"'" and token[-1] == token[0]:
                dict_key = token[1:-1]
                if not isinstance(current, dict) or dict_key not in current:
                    return None
                current = current[dict_key]
            else:
                return None  # e.g. [$count] — a shell variable we can't evaluate
        elif isinstance(current, dict) and name in current:
            current = current[name]
        else:
            return None
    return current


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


def _subprocess_fallback(stages: list[str]) -> list[str]:
    """
    Last-resort: hand the pipeline string to ``/bin/bash -c`` and capture
    stdout. Locked-down env (minimal PATH, no inherited variables), timeout,
    no shell expansion of our argv (we invoke bash explicitly with
    ``shell=False``). The pipeline string itself is still interpreted by
    bash, which is the accepted shell-injection surface area: callers opt
    in via ``allow_subprocess_fallback=True`` after pinning the Installomator
    commit hash and accepting the trust boundary.
    """
    pipeline = " | ".join(stages)
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", pipeline],
            capture_output=True,
            timeout=_SUBPROCESS_FALLBACK_TIMEOUT_SECONDS,
            text=True,
            env={"PATH": _SUBPROCESS_FALLBACK_PATH},
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UnsupportedOperation(
            f"subprocess fallback timed out after {_SUBPROCESS_FALLBACK_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise UnsupportedOperation(f"subprocess fallback could not start bash: {exc}") from exc

    if result.returncode != 0:
        stderr_snip = (result.stderr or "")[:200]
        raise UnsupportedOperation(
            f"subprocess fallback exited {result.returncode}: {stderr_snip!r}"
        )
    return [line for line in result.stdout.splitlines() if line]


def is_shell_expression(value: str | None) -> bool:
    """
    Detect whether an Installomator label value contains shell syntax that
    needs evaluation rather than being a usable literal.

    :func:`resolve` handles values shaped *exactly* like ``$(... pipeline ...)``
    (its regex is anchored). This helper is broader: it also catches embedded
    substitutions that ``resolve`` will pass through as literals, and which
    callers should treat as unsafe:

    - Pure expressions: ``$(curl -fsL https://...)`` or ``$varname``
    - Embedded substitutions: ``https://example.com$(curl ...)`` or
      ``${baseURL}/path/to/installer.pkg``

    Useful as a safety net after :func:`resolve` returns a literal value to
    confirm the literal is genuinely a clean value, not an unresolvable
    fragment that snuck past the resolver's anchored pattern.

    :param value: A parsed label-fragment value.
    :type value: str | None
    :return: ``True`` if the value contains any shell-expression artifacts.
    :rtype: bool
    """
    if value is None:
        return False
    if "$(" in value or "${" in value:
        return True
    return value.startswith("$")


def looks_like_clean_http_url(value: str | None) -> bool:
    """
    Sanity-check that ``value`` is a single, reasonably-sized http(s) URL
    safe to store in a column the API later serializes through Pydantic's
    ``HttpUrl`` type.

    Catches three classes of garbage :func:`resolve` can produce when a
    pipeline succeeds at the shell level but the captured output isn't a
    usable URL:

    - **HTML response bodies**: the upstream vendor returned a non-2xx
      response (404, 400, etc.) but ``curl`` didn't see it as an error, so
      the response body landed in the value. These typically start with
      ``<!doctype`` or ``<html``.
    - **Multi-line concatenations**: the Installomator pipeline's final
      filter was unsupported (e.g. ``awk`` or ``head -n1``), so the full
      ``grep`` output (every matched URL on the page, joined with
      newlines) landed in the value instead of a single line.
    - **Non-http schemes**: a handful of Installomator labels still use
      ``ftp://`` sources. Pydantic's ``HttpUrl`` rejects these and the
      catalog only documents http(s) URLs.

    Also enforces a 2000-character ceiling. Pydantic's ``HttpUrl`` maxes
    out at 2083 (the IE-era de-facto limit), so leaving 83 chars of
    headroom avoids edge cases at the boundary.

    :param value: Resolved or literal URL candidate.
    :type value: str | None
    :return: ``True`` when the value passes all sanity checks, ``False``
        otherwise (including for ``None`` and empty strings).
    :rtype: bool
    """
    if not value:
        return False
    if "\n" in value or "\r" in value:
        return False
    if len(value) > _MAX_URL_LENGTH:
        return False
    if not value.startswith(("http://", "https://")):
        return False
    if value.lstrip().startswith("<"):
        return False
    return True


def looks_like_clean_version(value: str | None) -> bool:
    """
    Sanity-check that ``value`` is a plausible version string, not pipeline garbage.

    ``appNewVersion`` has no schema-level guard (unlike ``downloadURL``, which
    Pydantic's ``HttpUrl`` validates downstream), so a pipeline that succeeds at
    the shell level but captures the wrong thing would otherwise store junk as a
    version. Empirically that junk is: empty output, whole HTML pages, HTTP
    header dumps, and un-``head``'d multi-line lists. Each is rejected here:

    - **Empty / whitespace-only**: nothing to store; the column should be ``NULL``.
    - **Multi-line**: a version is a single token. A newline means the final
      filter (``head -1`` etc.) was unsupported and the whole match list landed.
    - **HTML / markup**: an ``<`` or ``>`` means a page body, not a version.
    - **Over-length**: a real version is short; :data:`_MAX_VERSION_LENGTH`
      caps it well above any legitimate ``1.2.3-beta.4+build567`` shape.
    - **No digit**: every version carries a number; a digit-free string is a
      stray word or label, not a version.

    Internal spaces are *allowed* — a few labels legitimately produce
    ``"Build 4200"``-style versions, and the multi-line and markup rules already
    catch the header/HTML dumps that contain spaces.

    :param value: Resolved or literal version candidate.
    :type value: str | None
    :return: ``True`` when the value passes all sanity checks, ``False``
        otherwise (including for ``None`` and empty strings).
    :rtype: bool
    """
    if not value or not value.strip():
        return False
    if "\n" in value or "\r" in value:
        return False
    if "<" in value or ">" in value:
        return False
    if len(value) > _MAX_VERSION_LENGTH:
        return False
    return any(char.isdigit() for char in value)


def resolve(
    expression: str | None,
    *,
    http_client: httpx.Client | None = None,
    is_url: bool = False,
    is_version: bool = False,
    allow_subprocess_fallback: bool = False,
    context: dict | None = None,
) -> ResolveOutcome:
    """
    Resolve a single label value with a one-off :class:`PipelineResolver`.

    Convenience wrapper equivalent to ``PipelineResolver(http_client,
    allow_subprocess_fallback=...).resolve(expression, is_url=...)``. Callers
    resolving many labels in a batch should construct one
    :class:`PipelineResolver` and reuse it so a single ``httpx.Client`` is
    shared across all of them.

    :param expression: The label variable value as parsed from the ``.sh`` fragment.
    :type expression: str | None
    :param http_client: Optional pre-configured ``httpx.Client``; see
        :class:`PipelineResolver`.
    :type http_client: httpx.Client | None
    :param is_url: Run the result through :func:`looks_like_clean_http_url`.
    :type is_url: bool
    :param is_version: Run the result through :func:`looks_like_clean_version`.
    :type is_version: bool
    :param allow_subprocess_fallback: Opt into the ``bash`` fallback; see
        :class:`PipelineResolver`.
    :type allow_subprocess_fallback: bool
    :param context: Parsed label dict for sibling-variable resolution; see
        :class:`PipelineResolver`.
    :type context: dict | None
    :return: A :class:`Resolved`, :class:`Unresolvable`, or :class:`InvalidOutput`.
    :rtype: :class:`ResolveOutcome`
    """
    return PipelineResolver(
        http_client, allow_subprocess_fallback=allow_subprocess_fallback, context=context
    ).resolve(expression, is_url=is_url, is_version=is_version)
