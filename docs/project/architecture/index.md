---
description: "Patcher's internal architecture: the clients / core / cli package layout, PatcherClient composition, matching pipeline, async concurrency model, and hosted API workspace."
---

# Architecture

:::{rst-class} lead
How Patcher is put together, and why.
:::

---

Three internal packages, with the classes you'd actually reach for re-exported at the top level. `patcherctl` and `PatcherClient` run on the same domain code, so the CLI and the library always have the same features.

## The Three Internal Packages

::::{highlights}

`src/patcher/clients/`
: HTTP boundary. One wrapper per external service

`src/patcher/core/`
: Domain logic. No HTTP, no I/O outside of data manager

`src/patcher/cli/`
: Interactive surface and CLI entry point
::::

:::{dropdown} Package structure
```text
src/patcher/
├── clients/  
│   ├── __init__.py         # HTTPClient (httpx + truststore base)
│   ├── jamf.py             # JamfClient (Jamf Pro API)
│   ├── patcher_api.py      # PatcherAPIClient (api.patcherctl.dev catalog)
│   ├── installomator.py    # InstallomatorClient (label fetcher, standalone)
│   └── token_manager.py    # OAuth token lifecycle for Jamf
│
├── core/  
│   ├── patcher_client.py   # PatcherClient (the headline composer)
│   ├── matching.py         # Jamf title → catalog slug matching pipeline
│   ├── analyze.py          # TitleFilter / TrendAnalysis
│   ├── data_manager.py     # On-disk patch-data cache + export pipeline
│   ├── pdf_report.py       # PDF generation
│   ├── config_manager.py   # Credential resolution (keyring or in-memory)
│   ├── fonts.py            # Bundled-font discovery, download, asset copying
│   ├── exceptions.py       # PatcherError + subclasses
│   └── models/             # Pydantic 2 models (PatchTitle, PatcherSettings, etc.)
│
└── cli/  
    ├── __init__.py         # click group + command definitions (the entry point)
    ├── setup.py            # Interactive setup wizard
    ├── _console.py         # Terminal output layer: console, status, renderers, log handler
    └── _helpers.py         # CLI orchestration: arg parsing, cache, export workflow
```
:::

Imports only flow in one direction. `core/` never reaches into `cli/`, and `clients/` never reaches into either. CLI-only pieces like the status spinner, interactive prompts, and Rich-styled output all live in `cli/`. That one-way flow is what lets the library run on its own, without dragging in any CLI code.

:::{note}
`cli/setup.py` is the *one* exception to this rule as it must import from `clients/` and `core/` to drive the setup wizard.
:::

## Entry Point

{class}`~patcher.core.patcher_client.PatcherClient` is the main entry point. It owns three helpers that do the real work:

| Attribute | Type | Responsibility |
|---|---|---|
| `patcher.jamf` | {class}`~patcher.clients.jamf.JamfClient` | All Jamf Pro API traffic |
| `patcher.api` | {class}`~patcher.clients.patcher_api.PatcherAPIClient` | Patcher catalog reads (matching, label enrichment); `None` when `enable_matching=False` |
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

### Library Shortcuts

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

The three top-level methods (`fetch_patches`, `analyze`, `export`) exist so library callers don't have to remember which helper owns what. They're shortcuts. The underlying objects are still right there if you want to wire things up by hand.

## Matching Pipeline

The {meth}`~patcher.core.patcher_client.PatcherClient.fetch_patches` runs {func}`~patcher.core.matching.match_titles` to enrich Jamf patch titles with Installomator labels via the Patcher API.

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

## CLI as a Thin Wrapper

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

For example, `patcherctl export` resolves config, builds a `PatcherClient`, then delegates the actual fetch+export work to `process_reports()` in `cli/_helpers.py`. That orchestration is small. It threads CLI args into `PatcherClient` method calls and wraps the whole thing in a status spinner.

**What this means in practice:** if a feature can be expressed as "call this method on `PatcherClient`," it works the same from `patcherctl` and from a Python script. There's no private CLI-only menu the library is locked out of.

## Async-First

Almost everything is asynchronous. Patcher's HTTP transport is [`httpx`](https://www.python-httpx.org/) backed by [`truststore`](https://github.com/sethmlarson/truststore). Per-object concurrency is capped at 5 by default ([Jamf's recommended ceiling](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices)). The concurrency cap is enforced at two layers:

::::{markers}
:icon: octicon:shield-16

:::{marker} `asyncio.Semaphore(max_concurrency)`
On every `HTTPClient` subclass, gates how many in-flight requests can be outstanding.
:::

:::{marker} `httpx.Limits(max_connections=max_concurrency)`
On the underlying connection pool, bounds the actual TCP connection count.
:::
::::

In practice this means batch operations (e.g. fetching summaries for hundreds of titles) execute in flights of `max_concurrency`, with each batch waiting on the slowest request before kicking off the next.

### Practical Consequences

::::{markers}
:icon: octicon:light-bulb-16

:::{marker} Prefer `async with`
Library callers should prefer `async with PatcherClient(...) as patcher:` so connection pools (Jamf, Patcher API) are released cleanly. If you can't use `async with` (e.g. FastAPI startup hooks), call `await patcher.aclose()` manually.
:::

:::{marker} The CLI stays on one event loop
The wizard prompts use `asyncclick` to stay inside the same event loop as the rest of Patcher.
:::

:::{marker} Synchronous bridges
A few paths (e.g. the fonts download in `patcher.core.fonts`) use `httpx.get` directly with a `truststore.SSLContext`, so the same enterprise-CA story applies regardless of code path.
:::
::::

:::{seealso}

For more about SSL verification and TLS trust, see {ref}`SSL verification <ssl-verify>` in the install guide.
:::

## Token Lifecycle

Jamf API access uses an OAuth2 bearer token issued by Jamf and {class}`~patcher.clients.token_manager.TokenManager` handles the full lifecycle:

::::{steps}

:::{step} On first call, exchanges credentials for a token.

On first call, exchanges `client_id` and `client_secret` for an access token. Then writes `TOKEN` and `TOKEN_EXPIRATION` to the macOS keychain.
:::

:::{step} On subsequent calls, checks expiration.

On subsequent calls, reads the cached token and checks its expiration with a 5-minute safety margin.
:::

:::{step} Refreshes proactively when the margin is hit.

Refreshes proactively when the margin is hit. Library callers never have to think about token expiry. The TokenManager handles the refresh before the token lapses.
:::

::::

Library callers using `in_memory_credentials` get the same flow without keychain writes. The token still gets cached on the `JamfClient` instance for the process lifetime.

(in-memory-credentials)=

## Credential Resolution

`ConfigManager` resolves Jamf credentials from one of two places:

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0

:::{grid-item-card} {iconify}`octicon:key-16` Keychain
:class-card: outline

The default for `patcherctl`.

Credentials live in the macOS login keychain under service name `Patcher`. The setup wizard writes them, and the {class}`~patcher.clients.token_manager.TokenManager` updates the bearer token and expiration automatically.
:::

:::{grid-item-card} {iconify}`octicon:cpu-16` In-memory mode
:class-card: outline

Credentials are held only on the {class}`~patcher.core.config_manager.ConfigManager` instance for the duration of the process.

Engaged automatically when the CLI is invoked with all three credentials or matching env vars are provided. See {ref}`ci-cd` for the non-interactive flow.
:::
::::

:::{admonition} Important
:class: caution

A single `PatcherClient` instance is bound to **one** Jamf instance via one credential set. If you need to hit two Jamf tenants from the same script, create two `PatcherClient` objects.
:::

## Public Surface

```{code-block} python
:caption: The stable, importable surface is curated in `patcher`

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

Anything reachable via deeper paths (`patcher.cli.*`, `patcher.clients.HTTPClient`, `patcher.core.matching.match_titles`, etc.) is importable but **not** considered part of the stable surface. Internal refactors may shift it. CLI-only objects (e.g. `Setup`) are intentionally **not** re-exported from `patcher`.

## Patcher API Service

`patcher-api` is a separate workspace member living under `api/` in the monorepo. The service is reachable at <https://api.patcherctl.dev>. Catalog read endpoints are public.

:::{dropdown} Workspace layout
```text
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
:::

The workspace exists so the catalog service can ship on its own schedule, independent of the `patcherctl` PyPI package. For library users, the API is what `PatcherClient.fetch_patches` queries through `patcher.api`. You don't need to know about the workspace to use the library.

:::{seealso}

{doc}`/reference/api/endpoints` & {doc}`/reference/api/examples`
: For HTTP surface documentation.

{doc}`/reference/api/source/index`
: For module-level autodocs.

:::

### Data Flow

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

### Ingest Layer

`patcher_api/ingest/` has one module per upstream source. Each runs on the catalog-refresh schedule, pulls fresh data from its upstream, and writes rows into `app_source_details` for the stitch pipeline to consume. Adding a new source means writing one more ingest module that targets its own JSON column on `app_source_details`. No changes to the serving layer or the stitch logic structure required, just an additive entry in the per-field fallback chains.

:::{seealso}

{doc}`Stitching Pipeline </project/architecture/stitch>`
: How source-detail rows become canonical app records via per-field fallbacks.

{doc}`Resolution Pipeline </project/architecture/resolution>`
: How Installomator's dynamic shell fragments become concrete versions and URLs, across a Linux ingest server and a macOS runner.

{doc}`Upstream Sources </project/sources>`
: How Patcher integrates with Installomator, Homebrew, AutoPkg, and Jamf App Installers.

:::

### Serving Layer

A standard FastAPI app, with three nuances worth surfacing:

::::{markers}
:icon: octicon:gear-16

:::{marker} ETag middleware on `/apps*`
A weak ETag whose value is the SHA-256 of the underlying SQLite catalog file. The hash changes exactly when the catalog deploys (typically once per day, plus whenever a macOS runner pass uploads resolved values) and never otherwise. `If-None-Match` is parsed per RFC 7232, with both multi-value lists and the `*` wildcard honored. Revalidating clients short-circuit to 304 instantly between deploys, and Cloudflare absorbs the bulk of traffic in front of the origin.
:::

:::{marker} Admin-route hardening
Deploy tokens used by the macOS resolver runner carry an `expires_at` column (90-day default for new tokens; legacy NULL means never expires) and the `/admin/*` routes apply a per-IP rate limit on top of the token check. The token gate is fail-closed: no token configured means the endpoint refuses every request, so a misconfigured host can't accidentally expose a write surface.
:::

:::{marker} Lifespan composition
The FastAPI lifespan owns DB initialization, optional seeding, and catalog SHA computation. It also enters the MCP session manager's context so the mounted MCP sub-app's task group is running during the serving window.
:::
::::

### MCP Layer

`patcher_api/mcp/` is an ASGI sub-app mounted on the same FastAPI process at `/mcp`. It exposes the catalog over the [Model Context Protocol](https://modelcontextprotocol.io) so AI clients (Claude Desktop, Cursor, Claude Code, etc.) can query Patcher through natural-language tool calls. Same process, same SQLite, same lifespan.

:::{seealso}

{doc}`/guides/agents`
: Setup for AI clients

{doc}`/reference/mcp/index`
: Tool reference

{doc}`/project/architecture/stitch`
: The conceptual relationship to the rest of the API (the underlying catalog the MCP tools read from)

:::

### Intentional Duplication: `parse_fragment`

The workspace keeps its own copy of `parse_fragment` at `api/patcher_api/installomator/parser.py`, deliberately duplicated from `patcher.clients.installomator.parse_fragment` so the API side can ship on its own schedule without pulling in the `patcher` library. The two copies are documented as intentional twins; if parsing behavior changes, update both on purpose. The Installomator subsystem is co-located under `api/patcher_api/installomator/` for the same reason — keeping it in one place makes the divergence (or future re-convergence) easier to manage.


```{toctree}
:hidden:

stitch
resolution
```
