# Architecture

:::{rst-class} lead
Patcher is organized as three internal packages (`client/`, `core/`, `cli/`) with a small public surface in {mod}`patcher`. The CLI is a thin wrapper around `PatcherClient`; both surfaces share the same domain code.
:::

## The three internal packages

```
src/patcher/
├── client/         # HTTP boundary
│   ├── jamf.py             # JamfClient (Jamf Pro API)
│   ├── token_manager.py    # OAuth token lifecycle
│   └── __init__.py         # HTTPClient (httpx + truststore)
│
├── core/           # Domain logic
│   ├── patcher_client.py   # PatcherClient (the headline composer)
│   ├── analyze.py          # Filter / Trend criteria, Analyzer
│   ├── installomator.py    # InstallomatorClient (label matching)
│   ├── data_manager.py     # Caching + export pipeline
│   ├── pdf_report.py       # PDF generation
│   ├── config_manager.py   # Credential resolution (keyring or in-memory)
│   ├── exceptions.py       # PatcherError + friends
│   └── models/             # Pydantic 2 models (PatchTitle, etc.)
│
└── cli/            # Interactive surface
    ├── __init__.py         # patcherctl entry, subcommands, args
    ├── setup.py            # Interactive setup wizard
    ├── report.py           # CLI orchestration around PatcherClient
    ├── animation.py        # Spinner + progress UI
    ├── ui_manager.py       # PDF UI config (header/footer/font/logo)
    └── plist_manager.py    # macOS plist read/write
```

The boundary between layers is one-way: `core/` never imports from `cli/`, `client/` never imports from `core/` or `cli/`. Anything CLI-flavored (animation, plist persistence, interactive prompts) stays in `cli/`. This is what makes library use viable. You can import `core/` without dragging in keyring or asyncclick prompts.

:::{note}
The single exception worth knowing: `cli/setup.py` imports from `client/` and `core/` to drive the wizard. That's the expected direction.
:::

## `PatcherClient`: the entry point

{class}`~patcher.PatcherClient` is the headline composer. It owns the three collaborators that do real work:

| Attribute | Type | Responsibility |
|---|---|---|
| `patcher.jamf` | {class}`~patcher.JamfClient` | All Jamf Pro API traffic |
| `patcher.installomator` | {class}`~patcher.InstallomatorClient` | Label catalog + matching (or `None` if disabled) |
| `patcher.data` | {class}`~patcher.core.data_manager.DataManager` | Cache + export pipeline |

```python
from patcher import PatcherClient

async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://myorg.jamfcloud.com",
) as patcher:
    titles = await patcher.fetch_patches()           # uses jamf + installomator
    filtered = await patcher.analyze(titles, ...)    # uses data
    await patcher.export(filtered, ...)              # uses data
```

The three top-level methods on `PatcherClient` (`fetch_patches`, `analyze`, `export`) exist precisely to keep library callers from having to know which collaborator owns what. They're convenience orchestrators over the underlying primitives.

## CLI as a thin wrapper

`patcherctl` is built on [asyncclick](https://github.com/python-trio/asyncclick) and lives entirely in `cli/`. Each subcommand follows the same shape:

1. **Resolve config**: credentials from keychain (or env vars in non-interactive mode), UI config from plist.
2. **Construct a `PatcherClient`**: typically with `ConfigManager` populated by step 1.
3. **Call a top-level method**: `patcher.fetch_patches()`, `patcher.analyze()`, etc.
4. **Add CLI presentation**: spinner via {class}`~patcher.cli.animation.Animation`, styled echo, file persistence.

For example, `patcherctl export` resolves config, builds a `PatcherClient`, then delegates the actual fetch+export work to `process_reports()` in `cli/report.py`. The orchestration in `cli/report.py` is small. It threads CLI args into `PatcherClient` method calls and wraps the whole thing in an animation.

**What this means in practice:** if a feature can be expressed as "call this method on `PatcherClient`," it works the same from `patcherctl` and from a Python script. The CLI doesn't have private capabilities the library lacks.

## Async-first

Almost everything is `async`. Patcher's HTTP transport is [`httpx`](https://www.python-httpx.org/) backed by [`truststore`](https://github.com/sethmlarson/truststore) for TLS (see {ref}`SSL verification <ssl-verify>`). Per-`PatcherClient` concurrency is capped at 5 by default (Jamf's recommended ceiling); override with `concurrency=` if you've coordinated with the Jamf instance owner.

A few practical consequences:

- **Library callers should prefer `async with PatcherClient(...) as patcher:`** so the underlying `httpx` connection pool is released cleanly. If you can't use `async with` (e.g. FastAPI startup hooks), call `await patcher.aclose()` manually.
- **The CLI's wizard prompts use `asyncclick`** to stay inside the same event loop as the rest of Patcher.
- **Synchronous bridges** (e.g. fonts download in `UIConfigManager`) use `httpx.get` directly with a `truststore.SSLContext` so the same enterprise-CA story applies regardless of code path.

## Public surface

The stable, importable surface is curated in {mod}`patcher` itself:

```python
from patcher import (
    PatcherClient,         # top-level entry
    JamfClient,            # per-service clients
    InstallomatorClient,
    PatchTitle,            # return shapes
    PatchDevice,
    FilterCriteria,        # analysis enums
    TrendCriteria,
    PatcherError,          # exception base
    APIResponseError,      # ... and friends
    CredentialError,
    TokenError,
    InstallomatorWarning,
)
```

Anything reachable via deeper paths (`patcher.cli.*`, `patcher.client.HTTPClient`, etc.) is importable but **not** considered part of the stable surface. Internal refactors may shift it. CLI-only objects (`Setup`, `UIConfigManager`, `PropertylistManager`, `Animation`) are intentionally **not** re-exported from `patcher`.

## The hosted API service

`patcher-api` is a separate workspace member living under `api/` in the monorepo. It's a FastAPI service that exposes a public catalog of macOS patch metadata (Installomator + Homebrew Cask, eventually AutoPkg). It imports a small amount of code from `patcher.core.installomator` for label parsing, but is otherwise its own project with its own dependencies and tests.

For library users, the hosted API is something you might *consume* (see {doc}`/api/endpoints` for the surface). It's not part of `patcherctl`'s runtime.
