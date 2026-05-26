"""
Shell-tool emulation for the resolver's pipeline stages.

Each ``_exec_*`` function reimplements one shell filter (``grep``, ``sed``,
``awk``, ...) in pure Python — input lines in, output lines out — so
:mod:`patcher_api.installomator.resolver` can evaluate Installomator label
pipelines without invoking a shell. ``apply_filter`` is the dispatch the
resolver calls; everything else is module-private.

Only the highest-frequency invocation of each tool is supported; anything
richer raises :class:`UnsupportedOperation`, which the resolver turns into an
``Unresolvable`` (or hands to its opt-in subprocess fallback).
"""

import re

_AWK_PRINT_PATTERN = re.compile(r"^\{\s*print\s+\$(\d+)\s*\}$")
_SED_SUBST_PATTERN = re.compile(r"^s(.)(.*?)\1(.*?)\1([gimsx]*)$", re.DOTALL)


class UnsupportedOperation(Exception):
    """Raised when a pipeline contains a command the resolver doesn't handle."""


def apply_filter(cmd: str, args: list[str], input_lines: list[str]) -> list[str]:
    """Dispatch a pipeline filter stage to its emulator. The resolver's entry point."""
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
    if cmd == "xpath":
        return _exec_xpath(args, input_lines)
    raise UnsupportedOperation(f"Unsupported filter command: {cmd!r}")


def _parse_short_flags(arg: str) -> str:
    """``-fsIL`` → ``"fsIL"``. ``-f`` → ``"f"``. Non-flag → ``""``."""
    if arg.startswith("-") and not arg.startswith("--"):
        return arg[1:]
    return ""


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
        # BRE→PCRE: basic regex treats ( ) { } as literal and \( \) as groups.
        pattern = pattern.replace(r"\(", "(").replace(r"\)", ")")
        pattern = pattern.replace(r"\{", "{").replace(r"\}", "}")

    compiled = re.compile(pattern)
    count = 0 if global_replace else 1
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
    Minimal uniq implementation. Removes adjacent duplicates (mirroring real
    uniq's behavior, which is why pipelines typically sort first). Flags are
    not currently supported.
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


def _exec_xpath(args: list[str], input_lines: list[str]) -> list[str]:
    """
    Apply an XPath 1.0 expression to piped XML, mimicking macOS ``/usr/bin/xpath``.

    Labels feed an appcast / XML feed in and post-process the result with
    ``cut`` / ``sed``, so the *output format* must match the macOS tool or the
    downstream stages break: attribute matches print as ``name="value"`` (the
    label then does ``cut -d '"' -f2``); ``string()`` / ``text()`` matches print
    their text. Namespaced prefixes — notably ``sparkle:`` on appcasts — are
    resolved from the document's namespace map, with the canonical Sparkle URI
    as a fallback. lxml (not stdlib ElementTree) because the real expressions
    use ``string()``, predicates, ``contains()``, and ``following-sibling::``.

    Returns ``[]`` (→ ``Unresolvable``) on a parse error or no match rather than
    raising, so a flaky/changed feed degrades to a null column.
    """
    from lxml import etree  # heavy C extension; import only when xpath is used

    if not args:
        raise UnsupportedOperation("xpath requires an expression")
    expr = args[0]
    xml = "\n".join(input_lines).strip()
    if not xml:
        return []

    try:
        root = etree.fromstring(
            xml.encode("utf-8", "replace"), parser=etree.XMLParser(recover=True)
        )
    except etree.XMLSyntaxError:
        return []
    if root is None:
        return []

    nsmap = {prefix: uri for prefix, uri in root.nsmap.items() if prefix}
    nsmap.setdefault("sparkle", "http://www.andymatuschak.org/xml-namespaces/sparkle")

    try:
        results = root.xpath(expr, namespaces=nsmap)
    except etree.XPathError:
        return []

    # string()/number() return a bare scalar; node-sets return a list.
    if isinstance(results, str):
        stripped = results.strip()
        return [stripped] if stripped else []
    if not isinstance(results, list):
        text = str(results).strip()
        return [text] if text else []

    out: list[str] = []
    for item in results:
        if isinstance(item, etree._Element):
            text = (item.text or "").strip()
            if text:
                out.append(text)
        elif getattr(item, "is_attribute", False):
            # macOS xpath prints attributes as name="value"; labels cut on the quote.
            out.append(f'{item.attrname}="{item}"')
        else:  # text-node smart string
            text = str(item).strip()
            if text:
                out.append(text)
    return out
