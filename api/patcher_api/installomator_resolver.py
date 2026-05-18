"""
Shell expression resolution: the "pyinstallomator" subset.

Installomator labels frequently declare values via shell pipelines, e.g.::

    appNewVersion=$(curl -fsIL "https://download.mozilla.org/?product=firefox-latest" \\
      | grep -i ^location | cut -d "/" -f7)

The Patcher API ingestion pipeline needs the *resolved* value (e.g. "121.0")
rather than the raw shell expression. The functions below parse such
expressions and re-implement each pipeline stage in Python (no subprocess,
no shell evaluation, no sandboxing concerns), so resolution can run safely
against ~700 community-authored label snippets without executing any of them.

Supported vocabulary:
  - curl (flags: -f, -s, -I, -L; HEAD or GET; redirect-chain headers)
  - grep (flags: -i, -o, -v, -E)
  - head (-n N or -N)
  - tail (-n N or -N)
  - cut  (-d DELIM, -f SPEC; spec supports N, N1,N2, N1-N2)
  - awk  (only ``-F sep '{print $N}'``)
  - sed  (only ``s/X/Y/[g]``, with optional ``-E``)
  - tr   (translate + ``-d``)
  - sort (plain + ``-r`` + ``-n``)
  - uniq (adjacent dedup; no flags)

Patterns outside this vocabulary raise :class:`UnsupportedOperation`. Callers
can opt into :func:`_subprocess_fallback` (handing the pipeline to ``bash``)
by passing ``allow_subprocess_fallback=True``.

Historically lived under ``patcher.core.installomator``. Moved here because
resolution is a Patcher-API ingest concern, not a ``patcher`` package
concern — the package consumes resolved values via the API rather than
running pipelines itself.
"""

import re
import shlex
import subprocess
from dataclasses import dataclass

import httpx

_SHELL_EXPR_PATTERN = re.compile(r"^\$\((.*)\)\s*$", re.DOTALL)


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


_MAX_URL_LENGTH = 2000


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


class UnsupportedOperation(Exception):
    """Raised when a pipeline contains a command pyinstallomator doesn't yet handle."""


def resolve(
    expression: str | None,
    *,
    http_client: httpx.Client | None = None,
    is_url: bool = False,
    allow_subprocess_fallback: bool = False,
) -> ResolveOutcome:
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
    :param is_url: When ``True``, the resolved value is run through
        :func:`looks_like_clean_http_url` before returning. Failures land as
        :class:`InvalidOutput` so callers see "got something, rejected it"
        rather than "no value." Pass for fields whose projected column gets
        serialized as Pydantic ``HttpUrl``.
    :type is_url: bool
    :param allow_subprocess_fallback: When ``True``, pipelines that raise
        :class:`UnsupportedOperation` during native dispatch fall through to
        :func:`_subprocess_fallback`. Off by default because the fallback
        invokes ``bash`` on a public-repo string, which is a real (accepted)
        shell-injection surface area. Callers that pin the Installomator
        commit hash and trust the pipeline-string corpus can opt in.
    :type allow_subprocess_fallback: bool
    :return: A :class:`Resolved`, :class:`Unresolvable`, or :class:`InvalidOutput`.
    :rtype: :class:`ResolveOutcome`
    """
    if expression is None:
        return Unresolvable(reason="expression is None")

    match = _SHELL_EXPR_PATTERN.match(expression.strip())
    if not match:
        # Literal value, no pipeline evaluation.
        if is_url and not looks_like_clean_http_url(expression):
            return InvalidOutput(raw=expression, reason="literal but not a clean http(s) URL")
        return Resolved(value=expression)

    inner = match.group(1).strip()
    stages = _split_pipeline(inner)

    try:
        result_lines = _execute_pipeline(stages, http_client=http_client)
    except UnsupportedOperation as exc:
        if allow_subprocess_fallback:
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
    if is_url and not looks_like_clean_http_url(value):
        return InvalidOutput(raw=value, reason="resolved value failed URL sanity check")
    return Resolved(value=value)


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
    if cmd == "awk":
        return _exec_awk(args, input_lines)
    if cmd == "sed":
        return _exec_sed(args, input_lines)
    if cmd == "tr":
        return _exec_tr(args, input_lines)
    if cmd == "sort":
        return _exec_sort(args, input_lines)
    if cmd == "uniq":
        return _exec_uniq(args, input_lines)
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


_AWK_PRINT_PATTERN = re.compile(r"^\{\s*print\s+\$(\d+)\s*\}$")


def _exec_awk(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Minimal awk implementation. Supports only the highest-frequency
    Installomator pattern: ``awk -F <sep> '{print $N}'``.

    The full awk language (BEGIN/END blocks, regex patterns, conditionals,
    arithmetic) is intentionally not handled here; if a label uses anything
    richer, the dispatch raises :class:`UnsupportedOperation` and (when the
    caller has opted in) the subprocess fallback takes over.
    """
    delimiter = " "  # awk's default FS is "whitespace runs"; we approximate with space-split
    use_whitespace_split = True
    program: str | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-F" and i + 1 < len(args):
            delimiter = args[i + 1]
            use_whitespace_split = False
            i += 2
            continue
        if not arg.startswith("-") and program is None:
            program = arg
        i += 1

    if program is None:
        raise UnsupportedOperation("awk invocation has no program")

    match = _AWK_PRINT_PATTERN.match(program)
    if not match:
        raise UnsupportedOperation(f"awk program {program!r} not supported (only '{{print $N}}')")

    field_index = int(match.group(1))
    out: list[str] = []
    for line in input_lines:
        parts = line.split() if use_whitespace_split else line.split(delimiter)
        if 1 <= field_index <= len(parts):
            out.append(parts[field_index - 1])
        else:
            out.append("")
    return out


_SED_SUBST_PATTERN = re.compile(r"^s(.)(.*?)\1(.*?)\1([gimsx]*)$", re.DOTALL)


def _exec_sed(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Minimal sed implementation. Supports only the substitution form
    ``s/X/Y/`` (or ``s/X/Y/g``), optionally with the ``-E`` flag for extended
    regex. The delimiter can be any character (sed accepts ``s|X|Y|``,
    ``s#X#Y#``, etc.).

    Addresses, multi-line operations, hold-space tricks, and other sed
    features are intentionally unsupported. If a label uses them, dispatch
    raises :class:`UnsupportedOperation`.
    """
    extended = False
    program: str | None = None

    for arg in args:
        if arg in ("-E", "-r"):
            extended = True
            continue
        if not arg.startswith("-") and program is None:
            program = arg

    if program is None:
        raise UnsupportedOperation("sed invocation has no program")

    match = _SED_SUBST_PATTERN.match(program)
    if not match:
        raise UnsupportedOperation(f"sed program {program!r} not supported (only s/X/Y/[g])")

    _, pattern, replacement, flags = match.groups()
    global_replace = "g" in flags

    if not extended:
        # BRE-to-PCRE escape: in basic regex, ``(`` ``)`` ``{`` ``}`` are literal,
        # ``\(`` ``\)`` are groups. We do the minimum useful translation by
        # escaping the special-in-PCRE chars that BRE treats as literal.
        pattern = pattern.replace(r"\(", "(").replace(r"\)", ")")
        pattern = pattern.replace(r"\{", "{").replace(r"\}", "}")

    compiled = re.compile(pattern)
    count = 0 if global_replace else 1
    # Convert sed's ``\1`` backrefs to Python's ``\1`` (already same syntax)
    return [compiled.sub(replacement, line, count=count) for line in input_lines]


def _exec_tr(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Minimal tr implementation. Supports character translation (``tr X Y``)
    and deletion (``tr -d X``). Character classes like ``[:upper:]`` and
    ranges like ``a-z`` are not expanded.
    """
    delete_mode = False
    positional: list[str] = []

    for arg in args:
        if arg == "-d":
            delete_mode = True
            continue
        if not arg.startswith("-"):
            positional.append(arg)

    if delete_mode:
        if len(positional) != 1:
            raise UnsupportedOperation("tr -d expects exactly one set argument")
        delete_chars = set(positional[0])
        return ["".join(c for c in line if c not in delete_chars) for line in input_lines]

    if len(positional) != 2:
        raise UnsupportedOperation("tr translate expects exactly two set arguments")
    src, dst = positional
    if len(src) != len(dst):
        raise UnsupportedOperation("tr translate sets must be the same length")
    table = str.maketrans(src, dst)
    return [line.translate(table) for line in input_lines]


def _exec_sort(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Minimal sort implementation. Supports plain sort, ``-r`` reverse, and
    ``-n`` numeric. Locale, key, and merge flags are not supported.
    """
    reverse = False
    numeric = False
    for arg in args:
        flags = _parse_short_flags(arg)
        if not flags:
            if arg.startswith("-"):
                raise UnsupportedOperation(f"sort flag {arg!r} not supported")
            continue
        for f in flags:
            if f == "r":
                reverse = True
            elif f == "n":
                numeric = True
            else:
                raise UnsupportedOperation(f"sort flag '-{f}' not supported")

    if numeric:

        def key(line: str) -> tuple[int, float | str]:
            try:
                return (0, float(line.strip()))
            except ValueError:
                # Non-numeric lines sort after numerics, preserving textual order
                return (1, line)

        return sorted(input_lines, key=key, reverse=reverse)
    return sorted(input_lines, reverse=reverse)


def _exec_uniq(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Minimal uniq implementation. Removes adjacent duplicates (mirroring
    real uniq's behavior, which is why pipelines typically sort first).
    Flags are not currently supported.
    """
    for arg in args:
        if arg.startswith("-"):
            raise UnsupportedOperation(f"uniq flag {arg!r} not supported")

    out: list[str] = []
    previous: str | None = None
    for line in input_lines:
        if line != previous:
            out.append(line)
            previous = line
    return out


_SUBPROCESS_FALLBACK_TIMEOUT_SECONDS = 30.0
_SUBPROCESS_FALLBACK_PATH = "/usr/bin:/bin"


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
