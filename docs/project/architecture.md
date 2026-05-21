---
description: "Patcher's internal architecture: the clients / core / cli package layout, PatcherClient composition, matching pipeline, async concurrency model, and hosted API workspace."
---

# Architecture

:::{rst-class} lead
How Patcher is configured and why.
:::

Three internal packages, with the classes you'd actually reach for re-exported at the top level. `patcherctl` and `PatcherClient` share the same domain code by design. Feature parity isn't an afterthought, it's the whole point.

## The three internal packages

```
src/patcher/
├── clients/        # HTTP boundary — one wrapper per external service
│   ├── __init__.py         # HTTPClient (httpx + truststore base)
│   ├── jamf.py             # JamfClient (Jamf Pro API)
│   ├── patcher_api.py      # PatcherAPIClient (api.patcherctl.dev catalog)
│   ├── installomator.py    # InstallomatorClient (label fetcher, standalone)
│   └── token_manager.py    # OAuth token lifecycle for Jamf
│
├── core/           # Domain logic — no HTTP, no I/O outside the data manager
│   ├── patcher_client.py   # PatcherClient (the headline composer)
│   ├── matching.py         # Jamf title → catalog slug matching pipeline
│   ├── analyze.py          # TitleFilter / TrendAnalysis
│   ├── data_manager.py     # On-disk patch-data cache + export pipeline
│   ├── pdf_report.py       # PDF generation
│   ├── config_manager.py   # Credential resolution (keyring or in-memory)
│   ├── plist_manager.py    # macOS plist read/write (no UI)
│   ├── exceptions.py       # PatcherError + subclasses
│   └── models/             # Pydantic 2 models (PatchTitle, Label, etc.)
│
└── cli/            # Interactive surface — patcherctl entry point
    ├── __init__.py         # click group, subcommand registrations
    ├── setup.py            # Interactive setup wizard
    ├── report.py           # CLI orchestration around PatcherClient
    ├── animation.py        # Spinner + progress UI
    └── ui_manager.py       # PDF UI config (header/footer/font/logo) + interactive prompts
```

Imports only flow in one direction. `core/` never reaches into `cli/`, and `clients/` never reaches into either. CLI-only pieces like animation, interactive prompts, and click-styled output all live in `cli/`. This allows the library to be usable independently and separates concerns appropriately.

:::{note}
`cli/setup.py` is the *one* exception to this rule as it must import from `clients/` and `core/` to drive the setup wizard.
:::

## `PatcherClient`: the entry point

{class}`~patcher.core.patcher_client.PatcherClient` is the headline composer. It owns three collaborators that do real work:

| Attribute | Type | Responsibility |
|---|---|---|
| `patcher.jamf` | {class}`~patcher.clients.jamf.JamfClient` | All Jamf Pro API traffic |
| `patcher.api` | {class}`~patcher.clients.patcher_api.PatcherAPIClient` | Patcher catalog reads (matching, label enrichment); `None` when `enable_installomator=False` |
| `patcher.data` | {class}`~patcher.core.data_manager.DataManager` | On-disk patch-data cache + export pipeline |

```{mermaid}
graph LR
    PC[PatcherClient]
    PC --> JC[JamfClient]
    PC --> API[PatcherAPIClient]
    PC --> DM[DataManager]
    JC -.->|HTTPS| JAMF[(Jamf Pro)]
    API -.->|HTTPS| EXT[(api.patcherctl.dev)]
    DM -.->|read / write| FS[(~/Library/Caches/Patcher)]
```

```python
from patcher import PatcherClient

async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://myorg.jamfcloud.com",
) as patcher:
    titles = await patcher.fetch_patches()           # uses jamf + api
    filtered = await patcher.analyze(titles, ...)    # uses data
    await patcher.export(filtered, ...)              # uses data
```

The three top-level methods (`fetch_patches`, `analyze`, `export`) exist so library callers don't have to remember which collaborator owns what. They're shortcuts; the underlying primitives are still right there if you want to wire things up by hand.

## Matching pipeline

`fetch_patches` runs `core/matching.py::match_titles` to enrich Jamf patch titles with Installomator labels via the Patcher API:

1. Fetch the slug set: `api.list_apps(source="installomator", limit=1000)` returns every Installomator-tracked app in the stitched catalog.
2. Fetch per-title app names from Jamf via `jamf.get_app_names`.
3. For each title, match its Jamf-side app names against the slug set in three passes: direct → normalized (lowercase, dots stripped) → fuzzy (rapidfuzz ratio, threshold 85).
4. Attach name-only `Label` stubs to matched titles' `install_label` list.
5. Run a second pass on still-unmatched titles using the patch-title text itself.
6. Write everything that never matched to `~/Library/Application Support/Patcher/unmatched_apps.json` for review, and emit an `InstallomatorWarning` via Python's `warnings` module so library callers can catch / escalate programmatically. The CLI installs `warnings.simplefilter("always", InstallomatorWarning)` at import time so end users always see the message.

```{mermaid}
flowchart TD
    A[Jamf patch titles] --> P{For each title}
    SS[api.list_apps -> slug set] --> P
    AN[jamf.get_app_names -> app names] --> P
    P --> D[Direct match]
    D -- hit --> Z[Attach Label stub]
    D -- miss --> N[Normalized match]
    N -- hit --> Z
    N -- miss --> F[Fuzzy match]
    F -- hit --> Z
    F -- miss --> S[Second pass<br/>on patch title text]
    S -- hit --> Z
    S -- miss --> U[Write to unmatched_apps.json]
```

The slug set comes from the API in one HTTP call instead of pulling `Labels.txt` and a fragment per label straight from GitHub. Same match quality, lower latency, and fewer GitHub rate-limit headaches on a busy fleet.

## CLI as a thin wrapper

`patcherctl` is built on [asyncclick](https://github.com/python-trio/asyncclick) and lives entirely in `cli/`. Each subcommand follows the same shape:

1. **Resolve config**: credentials from keychain (or env vars in non-interactive mode), UI config from plist.
2. **Construct a `PatcherClient`**: typically with `ConfigManager` populated by step 1.
3. **Call a top-level method**: `patcher.fetch_patches()`, `patcher.analyze()`, etc.
4. **Add CLI presentation**: spinner via {class}`~patcher.cli.animation.Animation`, styled echo, file persistence.

For example, `patcherctl export` resolves config, builds a `PatcherClient`, then delegates the actual fetch+export work to `process_reports()` in `cli/report.py`. The orchestration in `cli/report.py` is small. It threads CLI args into `PatcherClient` method calls and wraps the whole thing in an animation.

**What this means in practice:** if a feature can be expressed as "call this method on `PatcherClient`," it works the same from `patcherctl` and from a Python script. There's no private CLI-only menu the library is locked out of.

## Async-first

Almost everything is `async`. Patcher's HTTP transport is [`httpx`](https://www.python-httpx.org/) backed by [`truststore`](https://github.com/sethmlarson/truststore) for TLS (see {ref}`SSL verification <ssl-verify>`). Per-`PatcherClient` concurrency is capped at 5 by default ([Jamf's recommended ceiling](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices)); override with `concurrency=` if you've coordinated with the Jamf instance owner.

The concurrency cap is enforced at two layers:

- An `asyncio.Semaphore(max_concurrency)` on every `HTTPClient` subclass gates how many in-flight requests can be outstanding.
- `httpx.Limits(max_connections=max_concurrency)` on the underlying connection pool bounds the actual TCP connection count.

In practice this means batch operations (e.g. fetching summaries for hundreds of titles) execute in flights of `max_concurrency`, with each batch waiting on the slowest request before kicking off the next.

A few practical consequences:

- **Library callers should prefer `async with PatcherClient(...) as patcher:`** so connection pools (Jamf + Patcher API) are released cleanly. If you can't use `async with` (e.g. FastAPI startup hooks), call `await patcher.aclose()` manually.
- **The CLI's wizard prompts use `asyncclick`** to stay inside the same event loop as the rest of Patcher.
- **Synchronous bridges** (e.g. fonts download in `UIConfigManager`) use `httpx.get` directly with a `truststore.SSLContext` so the same enterprise-CA story applies regardless of code path.

## Token lifecycle

Jamf API access uses an OAuth2 bearer token issued by Jamf. {class}`~patcher.clients.token_manager.TokenManager` handles the full lifecycle:

1. On first call, exchanges `client_id` + `client_secret` for an access token and writes `TOKEN` + `TOKEN_EXPIRATION` to the macOS keychain.
2. On subsequent calls, reads the cached token and checks its expiration with a 5-minute safety margin.
3. Refreshes proactively when the margin is hit. Library callers never have to think about token expiry; the TokenManager handles the whole "your bearer is about to expire" dance behind the scenes.

Library callers using `in_memory_credentials` (see {ref}`below <in-memory-credentials>`) get the same flow without keychain writes. The token still gets cached on the `JamfClient` instance for the process lifetime.

(in-memory-credentials)=

## Credential resolution

`ConfigManager` resolves Jamf credentials from one of two sources:

- **Keychain mode** (the default for `patcherctl`): credentials live in the macOS login keychain under service name `Patcher`. The setup wizard writes them; the `TokenManager` updates `TOKEN` and `TOKEN_EXPIRATION` automatically.
- **In-memory mode** (`in_memory_credentials=True`): credentials are held only on the `ConfigManager` instance for the duration of the process. Engaged automatically when `patcherctl` is invoked with all three of `--client-id`, `--client-secret`, `--url` (or the matching `PATCHER_*` env vars), and used directly by library callers who pass credentials to `PatcherClient.__init__`. See {ref}`ci-cd` for the non-interactive flow.

There's no multi-tenant story today. A `PatcherClient` instance is bound to one Jamf instance via one credential set. If you need to hit two Jamf tenants from the same script, that's two `PatcherClient` objects.

## Public surface

The stable, importable surface is curated in ``patcher`` itself:

```python
from patcher import (
    PatcherClient,         # top-level entry
    JamfClient,            # per-service clients
    InstallomatorClient,
    PatcherAPIClient,
    PatchTitle,            # return shapes
    PatchDevice,
    TitleFilter,           # analysis surface
    TrendAnalysis,
    PatcherError,          # exception base
    APIResponseError,      # ... and friends
    CredentialError,
    TokenError,
    InstallomatorWarning,
)
```

Anything reachable via deeper paths (`patcher.cli.*`, `patcher.clients.HTTPClient`, `patcher.core.matching.match_titles`, etc.) is importable but **not** considered part of the stable surface. Internal refactors may shift it. CLI-only objects (`Setup`, `UIConfigManager`, `Animation`) are intentionally **not** re-exported from `patcher`.

## The hosted Patcher API service

`patcher-api` is a separate workspace member living under `api/` in the monorepo. It's a FastAPI service that exposes a public catalog of macOS app patching metadata stitched from five sources (Installomator, Homebrew Cask, AutoPkg, MAS, and the Jamf App Installers index). The service is deployed at <https://api.patcherctl.dev>; the catalog reads are public, with only the admin `/admin/*` endpoints gated behind deploy tokens.

Admin-route hardening: deploy tokens carry an `expires_at` column (90-day default for new tokens; legacy NULL = never expires), and the `/admin/*` routes apply a `slowapi` per-IP rate limit (12 requests per hour) on top of the token check. Catalog reads on `/apps*` use a weak ETag whose value is the SHA-256 of the underlying SQLite catalog, with `If-None-Match` parsed per RFC 7232 (multi-value list and the `*` wildcard both honored).

The workspace keeps its own copy of `parse_fragment` at `api/patcher_api/ingest/_label_parser.py`, deliberately duplicated from `patcher.clients.installomator.parse_fragment` so the api side ships on its own schedule without pulling in the library. The two copies are documented as intentional twins; if parsing behavior changes, update both on purpose. Everything else (the resolver that evaluates shell pipelines, the per-source ingest modules, the stitch logic, the FastAPI app itself) lives under `api/patcher_api/` with its own dependencies, tests, and deploy pipeline.

For library users, the hosted API is what `PatcherClient.fetch_patches` queries through `patcher.api`. You don't need to know about the workspace to use the library; the workspace exists because deploying the catalog service is independent from shipping the patcherctl Python package. See {doc}`/reference/api/endpoints` for the API surface.
