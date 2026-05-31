---
description: "Patcher's internal architecture: the clients / core / cli package layout, PatcherClient composition, matching pipeline, async concurrency model, and hosted API workspace."
---

# Architecture

:::{rst-class} lead
How Patcher is configured and why.
:::

---

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
    ├── _console.py         # Rich console singletons + status spinner
    └── ui_manager.py       # PDF UI config (header/footer/font/logo) + interactive prompts
```

Imports only flow in one direction. `core/` never reaches into `cli/`, and `clients/` never reaches into either. CLI-only pieces like the status spinner, interactive prompts, and Rich-styled output all live in `cli/`. This allows the library to be usable independently and separates concerns appropriately.

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

::::{steps}

:::{step} Fetch the slug set.

`api.list_apps(source="installomator", limit=1000)` returns every Installomator-tracked app in the stitched catalog.
:::

:::{step} Fetch per-title app names from Jamf.

Fetch per-title app names from Jamf via `jamf.get_app_names`.
:::

:::{step} Match against the slug set in three passes.

For each title, match its Jamf-side app names against the slug set in three passes: direct → normalized (lowercase, dots stripped) → fuzzy (rapidfuzz ratio, threshold 85).
:::

:::{step} Attach `Label` stubs to matched titles.

Attach name-only `Label` stubs to matched titles' `install_label` list.
:::

:::{step} Run a second pass on unmatched titles.

Run a second pass on still-unmatched titles using the patch-title text itself.
:::

:::{step} Write out what never matched.

Write everything that never matched to `~/Library/Application Support/Patcher/unmatched_apps.json` for review, and emit an `InstallomatorWarning` via Python's `warnings` module so library callers can catch / escalate programmatically. The CLI installs `warnings.simplefilter("always", InstallomatorWarning)` at import time so end users always see the message.
:::

::::

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

::::{steps}

:::{step} Resolve config

credentials from keychain (or env vars in non-interactive mode), UI config from plist.
:::

:::{step} Construct a `PatcherClient`

typically with `ConfigManager` populated by step 1.
:::

:::{step} Call a top-level method

`patcher.fetch_patches()`, `patcher.analyze()`, etc.
:::

:::{step} Add CLI presentation

spinner via the `status()` helper in `cli/_console.py`, Rich-styled output, file persistence.
:::

::::

For example, `patcherctl export` resolves config, builds a `PatcherClient`, then delegates the actual fetch+export work to `process_reports()` in `cli/report.py`. The orchestration in `cli/report.py` is small. It threads CLI args into `PatcherClient` method calls and wraps the whole thing in a status spinner.

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

::::{steps}

:::{step} On first call, exchanges credentials for a token.

On first call, exchanges `client_id` + `client_secret` for an access token and writes `TOKEN` + `TOKEN_EXPIRATION` to the macOS keychain.
:::

:::{step} On subsequent calls, checks expiration.

On subsequent calls, reads the cached token and checks its expiration with a 5-minute safety margin.
:::

:::{step} Refreshes proactively when the margin is hit.

Refreshes proactively when the margin is hit. Library callers never have to think about token expiry; the TokenManager handles the whole "your bearer is about to expire" dance behind the scenes.
:::

::::

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

Anything reachable via deeper paths (`patcher.cli.*`, `patcher.clients.HTTPClient`, `patcher.core.matching.match_titles`, etc.) is importable but **not** considered part of the stable surface. Internal refactors may shift it. CLI-only objects (`Setup`, `UIConfigManager`) are intentionally **not** re-exported from `patcher`.

## The hosted Patcher API service

`patcher-api` is a separate workspace member living under `api/` in the monorepo. It's a FastAPI service exposing a public catalog of macOS app patching metadata stitched from five sources (Installomator, Homebrew Cask, AutoPkg, Mac App Store, and Jamf App Installers). The service is reachable at <https://api.patcherctl.dev>. Catalog reads are public; admin upserts are token-gated.

The workspace exists so the catalog service can ship on its own schedule, independent of the `patcherctl` PyPI package. For library consumers, the API is what `PatcherClient.fetch_patches` queries through `patcher.api`; you don't need to know about the workspace to use the library. For the HTTP surface see {doc}`/reference/api/endpoints` and {doc}`/reference/api/examples`; for module-level autodoc see {doc}`/reference/api/source/index`.

### Workspace layout

```
api/patcher_api/
├── main.py                  # FastAPI app + lifespan + ETag middleware + /mcp mount
├── config.py                # pydantic-settings, env-var-driven
├── db.py                    # async SQLAlchemy engine + session, SQLite-tuned pragmas
├── catalog.py               # SHA-256 of the catalog file for ETag derivation
├── stitch.py                # canonical-row projection (see concept page)
├── drift.py                 # cross-source version disagreement detection
├── labels.py                # Installomator-shaped label fragment builder
├── seed.py                  # smoke seed for empty DBs
├── ingest/                  # per-source pullers (homebrew, autopkg, jamf, mas)
├── installomator/           # parser, resolver, ingest (co-located subsystem)
├── routes/
│   ├── apps.py              # public catalog reads
│   └── admin.py             # token-gated upserts from the macOS resolver runner
├── mcp/                     # MCP server (Streamable HTTP, mounted at /mcp)
│   ├── server.py
│   ├── tools.py
│   └── middleware.py        # Origin validation per MCP spec
├── models/                  # SQLAlchemy ORM models
└── schemas/                 # Pydantic models for response serialization
```

### Data flow

```{mermaid}
flowchart LR
    subgraph EXT [Upstream sources]
      direction TB
      INST[Installomator]
      CASK[Homebrew Cask]
      AP[AutoPkg]
      MAS[Mac App Store]
      JAI[Jamf App Installers]
    end

    EXT --> ING[Ingest modules]
    ING --> SD[(app_source_details)]

    MACR[macOS GitHub<br/>Actions runner] -- POST /admin/labels/resolved --> ADM[Admin route]
    ADM --> SD

    SD --> ST[Stitch] --> APPS[(apps)]

    APPS --> APP_R[/apps* routes/]
    APPS --> MCP[/mcp tools/]

    APP_R -.->|JSON| CLIENT1[REST clients<br/>PatcherAPIClient]
    MCP -.->|JSON-RPC| CLIENT2[MCP clients<br/>Claude, Cursor, etc.]
```

### Ingest layer

`patcher_api/ingest/` has one module per upstream source. Each runs on the catalog-refresh schedule, pulls fresh data from its upstream, and writes rows into `app_source_details` for the stitch pipeline to consume. Sources currently covered: Installomator (with its own parser + resolver dance described below), Homebrew Cask (JSON catalog from the brew API), AutoPkg (recipe repos cloned and parsed for app metadata), Jamf App Installers (the public title catalog scraped for coverage signal), and Mac App Store (bundle-ID lookups against the iTunes API).

Adding a new source means writing one more ingest module that targets its own JSON column on `app_source_details`. No changes to the serving layer or the stitch logic structure required, just an additive entry in the per-field fallback chains.

### Stitch and resolution

Two domain pipelines worth following in their own pages:

- {doc}`/project/pipelines/stitch` — how source-detail rows become canonical `apps` records via per-field fallback chains.
- {doc}`/project/pipelines/resolution` — how Installomator's dynamic shell fragments become concrete versions and URLs via a Linux-ingest / macOS-runner producer-consumer split.

### Serving layer

A standard FastAPI app, with three nuances worth surfacing:

- **ETag middleware on `/apps*`.** A weak ETag whose value is the SHA-256 of the underlying SQLite catalog file. The hash changes exactly when the catalog deploys (typically once per day, plus whenever a macOS runner pass uploads resolved values) and never otherwise. `If-None-Match` is parsed per RFC 7232, with both multi-value lists and the `*` wildcard honored. Revalidating clients short-circuit to 304 instantly between deploys; Cloudflare absorbs the bulk of traffic in front of the origin.
- **Admin-route hardening.** Deploy tokens used by the macOS resolver runner carry an `expires_at` column (90-day default for new tokens; legacy NULL means never expires) and the `/admin/*` routes apply a per-IP rate limit on top of the token check. The token gate is fail-closed: no token configured means the endpoint refuses every request, so a misconfigured host can't accidentally expose a write surface.
- **Lifespan composition.** The FastAPI lifespan owns DB initialization, optional seeding, and catalog SHA computation. It also enters the MCP session manager's context so the mounted MCP sub-app's task group is running during the serving window.

### MCP layer

`patcher_api/mcp/` is an ASGI sub-app mounted on the same FastAPI process at `/mcp`. It exposes the catalog over the [Model Context Protocol](https://modelcontextprotocol.io) so AI clients (Claude Desktop, Cursor, Claude Code, etc.) can query Patcher through natural-language tool calls. Same process, same SQLite, same lifespan; just a different transport.

The MCP server is reachable publicly at <https://mcp.patcherctl.dev>. Setup for AI clients lives in {doc}`/guides/usage/agents`; tool reference at {doc}`/reference/mcp/index`; the conceptual relationship to the rest of the API is described in {doc}`/project/pipelines/stitch` (the underlying catalog the MCP tools read from).

### Intentional duplication: `parse_fragment`

The workspace keeps its own copy of `parse_fragment` at `api/patcher_api/installomator/parser.py`, deliberately duplicated from `patcher.clients.installomator.parse_fragment` so the API side can ship on its own schedule without pulling in the `patcher` library. The two copies are documented as intentional twins; if parsing behavior changes, update both on purpose. The Installomator subsystem is co-located under `api/patcher_api/installomator/` for the same reason — keeping it in one place makes the divergence (or future re-convergence) easier to manage.
