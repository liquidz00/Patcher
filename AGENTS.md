# AGENTS.md

Instructions for AI coding agents working on Patcher. Tool-agnostic; applies
equally to Claude Code, Cursor, Aider, or any other coding assistant.

## What Patcher is

A Python library **and** CLI for MacAdmins that pulls patch management data
from the Jamf Pro API and exports reports in Excel, HTML, PDF, and JSON
formats. Distributed as the `patcherctl` command via PyPI (project name:
`patcherctl`, package name: `patcher`). The library entry point is
`patcher.PatcherClient`; anything you can do via the CLI is also doable
programmatically.

There is also a separate **Patcher API** service (workspace member at `api/`,
package name `patcher-api`) that exposes a public read-only catalog of macOS
app patching metadata ingested from Installomator, Homebrew Cask, and
AutoPkg sources, then stitched into a unified shape. The API depends on
`patcherctl` via the uv workspace to share Installomator parsing and the
shell-expression resolver. Treat the API as a separate deliverable from
patcherctl. Its deps, tests, and deployment story are distinct.

**When adding new features to patcherctl**, prefer pure functions and classes
usable outside the Click context. The CLI is a thin wrapper, not the core.
Library-callers (and the API) depend on the underlying logic having no
hidden CLI assumptions.

## Quick start

```bash
# Set up dev environment (uv handles the venv + deps across all workspace members)
make dev                      # uv sync --all-packages --all-extras

# Run the CLI locally
uv run patcherctl --help

# Run the API locally (auto-reload)
make serve-api                # cd api && uv run uvicorn patcher_api.main:app --reload

# Common make targets
make test               # patcherctl unit tests (excludes integration)
make test-api           # patcher-api tests
make test-integration   # patcherctl integration tests against dummy.jamfcloud.com
make lint               # ruff format --check + ruff check
make format             # ruff format (does NOT remove unused imports; use lint for that)
make docs               # sphinx-build -b html docs/ docs/_build/
```

Pre-commit hooks are configured (`.pre-commit-config.yaml`). They run on every
commit and must pass. Install once with `pre-commit install`.

## Project layout

The repo is a uv workspace with two packages: `patcherctl` at the root (the
library + CLI) and `patcher-api` under `api/` (the public catalog service).

```
src/patcher/                  # the patcherctl package (library + CLI)
├── __init__.py               # Public surface: PatcherClient, JamfClient,
│                             # InstallomatorClient, PatchTitle, PatchDevice, exceptions
├── __about__.py              # __version__ (read dynamically by pyproject.toml)
├── client/                   # HTTP transport, no CLI/keyring deps
│   ├── __init__.py           # HTTPClient (generic httpx + truststore plumbing)
│   ├── jamf.py               # JamfClient (Jamf Pro-specific endpoints)
│   └── token_manager.py      # OAuth client_credentials flow, token lifecycle
├── core/                     # Domain logic + library entry point
│   ├── patcher_client.py     # PatcherClient: top-level library entry,
│   │                         # composes JamfClient + InstallomatorClient + DataManager
│   ├── installomator.py      # InstallomatorClient (label fetch + match),
│   │                         # parse_fragment(), and resolve() (the
│   │                         # pyinstallomator shell-expression evaluator)
│   ├── config_manager.py     # Keychain (or in-memory) credential storage
│   ├── data_manager.py       # Caching, DataFrame mgmt, export() entrypoint,
│   │                         # serialize_titles_to_dict()
│   ├── analyze.py            # Sort/filter/iOS-status transforms over
│   │                         # list[PatchTitle] (module-level functions,
│   │                         # the legacy ReportManager was retired here)
│   ├── pdf_report.py         # FPDF rendering (takes a UI config dict,
│   │                         # falls back to Helvetica when font paths absent)
│   ├── fonts.py              # ensure_default_fonts(target_dir): standalone
│   │                         # font downloader for library callers
│   ├── exceptions.py         # PatcherError + subclasses
│   ├── logger.py             # PatcherLog, LogMe (stdlib only)
│   └── models/               # Pydantic 2 schemas
│       ├── patch.py          # PatchTitle, PatchDevice
│       ├── jamf.py           # JamfCredentials
│       ├── token.py          # AccessToken
│       ├── label.py          # Installomator Label
│       ├── ui.py             # UI config schema
│       └── fragment.py
└── cli/                      # CLI surface (asyncclick, depends on click + Click context)
    ├── __init__.py           # click entry point; commands: setup, reset, export, analyze
    ├── setup.py              # Interactive + non-interactive setup flow
    ├── report.py             # process_reports (now takes a PatcherClient)
    ├── plist_manager.py      # ~/Library/Application Support/Patcher/...plist persistence
    ├── ui_manager.py         # Plist-coupled UI config + interactive setup integration
    ├── animation.py          # Terminal spinner
    └── terminal_logger.py    # Click-styled logging adapter (only when --debug)

api/                          # patcher-api workspace member (the API service)
├── patcher_api/
│   ├── main.py               # FastAPI app + lifespan (init_db + optional seed)
│   ├── config.py             # Pydantic BaseSettings (env-driven, PATCHER_API_* prefix)
│   ├── db.py                 # Async SQLAlchemy engine + session factory + init_db()
│   ├── auth.py               # Bearer-token auth dependency (SHA-256 hashed at rest)
│   ├── seed.py               # Idempotent first-boot seeding from data.py
│   ├── data.py               # In-memory SEED_APPS + SEED_SOURCES for bootstrap/tests
│   ├── labels.py             # Installomator label generator (projects DB → label JSON)
│   ├── stitch.py             # Catalog stitch (Installomator + Homebrew Cask → apps rows)
│   ├── routes/               # FastAPI routers (apps.py: list/get/sources/generate-label)
│   ├── schemas/              # Pydantic request/response shapes
│   ├── models/               # SQLAlchemy ORM (App, AppSourceDetail, HomebrewCask,
│   │                         # InstallomatorLabel, Token)
│   └── ingest/               # Upstream ingestion (homebrew.py, installomator.py)
├── scripts/                  # Standalone CLI utilities: grant_token.py,
│                             # ingest_homebrew.py, ingest_installomator.py,
│                             # stitch_catalog.py
└── tests/                    # patcher-api tests (separate from patcherctl tests)

tests/                        # patcherctl tests (flat, conftest.py for shared fixtures)
docs/                         # Sphinx + MyST + Shibuya theme
                              # getting-started/, usage/, integrations/, concepts/,
                              # api/, reference/, contributing/, faq.md, troubleshooting.md
vendor-docs/                  # Upstream Installomator + AutoPkg wikis (git submodules)
```

## Conventions

### Code style
- **Ruff** for linting + formatting. `make lint` is the source of truth.
  `make format` only fixes formatting, not lint issues like unused imports.
- **Line length 100**, double quotes, target Python 3.11+ (verified in CI on 3.11, 3.12, 3.13, 3.14).
- **Modern union syntax** (`str | None`, `dict | int`), NOT `Optional[str]`,
  NOT `Union[str, int]`. The Cursor rule on this is out of date relative to
  the actual code; trust the code.
- **Sphinx/reST docstrings** for every public function, method, and class.
  Use `:param:`, `:type:`, `:return:`, `:rtype:`, `:raises:`. Do NOT use
  Google or NumPy docstring style. See `.cursor/rules/sphinx-style-docstrings.mdc`.
- **PEP 8 naming**: `snake_case` for funcs/vars, `PascalCase` for classes,
  `UPPER_CASE` for constants. PascalCase mock vars in `tests/` are exempt
  from `N806` (configured in `pyproject.toml`).
- **Type hints on everything**, including params and return types for
  private methods.

### Async-first
Most of the codebase is async. CLI is built on `asyncclick`. New API-touching
code should be async. When you need to call sync code from async context, use
`asyncio.to_thread`.

### Pydantic 2
All models inherit from `BaseModel`. Serialize with `.model_dump(mode="json")`
when producing JSON output; preserves enum values, datetimes, and nested
structures correctly. `.model_dump()` (no mode) returns Python natives.

### Errors
Custom exceptions live in `core/exceptions.py`. All inherit from `PatcherError`.
Surface user-facing errors via `PatcherError(...)` with `key=value` kwargs
that get rendered in the message. The CLI's `__main__` catches by type and
sets specific exit codes:

| Exit | Reason |
|---|---|
| 0 | Success |
| 1 | PatcherError (general user-facing) |
| 2 | Unhandled exception |
| 3 | SetupError |
| 4 | APIResponseError |
| 130 | KeyboardInterrupt |

### Commits
Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`,
`build:`, `ci:`). Pre-commit + ruff + format-check enforced on every commit.

## Testing

- `pytest` + `pytest-asyncio` + `pytest-mock`. `unittest.mock` for patching.
- Tests are in `tests/`. Unit tests are flat at the top level; integration
  tests live in `tests/integration/`. Shared unit-test fixtures in
  `tests/conftest.py`; integration-specific fixtures in
  `tests/integration/conftest.py`.
- All async tests must be decorated with `@pytest.mark.asyncio`.
- **No dedicated live Jamf Pro instance** is available for testing. Every
  unit test that touches the API surface must mock the relevant client
  (`ApiClient`, `BaseAPIClient`, `TokenManager`). Mock-based tests are the
  primary safety net.
- **Integration tests against `dummy.jamfcloud.com`** (Jamf's published
  public test instance) are available via `make test-integration`, opt-in
  and excluded from the default `make test`. Use them as a smoke layer for
  significant changes (e.g. transport migrations), but they are NOT a
  substitute for mocked unit tests, since the dummy instance data isn't
  comprehensive. See `docs/contributing/index.rst` for details.
- **Mock-friendly design**: when adding new API-touching code, isolate the
  HTTP call in a method that's easy to mock at the test boundary. Don't mix
  business logic and HTTP construction in one place.

## Non-interactive / CI/CD mode

Patcher supports running without keychain access via `--client-id` /
`--client-secret` / `--url` flags or `PATCHER_CLIENT_ID` /
`PATCHER_CLIENT_SECRET` / `PATCHER_URL` env vars. When all three are present,
`ConfigManager(in_memory_credentials={...})` is used and the keychain is
never touched. See `docs/usage/automation.md` for the user-facing contract.

When adding features, **don't break this**: avoid hardcoding paths to
`~/Library/Application Support/...` or assuming a macOS keychain backend
exists. Anything that needs credentials should go through `ConfigManager`,
which abstracts the storage backend.

## Things to be careful about

These are known rough spots. Don't refactor them as part of an unrelated PR;
file an issue and tackle separately.

- **`Setup` flow** (`cli/setup.py`): the `SetupStage` state machine was
  retired in favor of a linear `start()` flow, but the underlying setup
  surface still has more branches than it strictly needs
  (interactive/noninteractive, Standard/SSO Jamf integrations, font/logo
  config). `Setup.bootstrap_noninteractive` is the CI/CD path.
- **`DataManager` is large** (`core/data_manager.py`): caching, validation,
  export, filename generation, DataFrame conversion all in one class.
  Splitting would help but is a noisy refactor.
- **`InstallomatorClient.match()` fuzzy logic** (`core/installomator.py`):
  direct → normalized → rapidfuzz fallback chain is effective but has many
  knobs (`threshold`, `_normalize` rules). Adjust gingerly; consequences
  show up as missing or wrong label matches.
- **The patcher-api ↔ patcherctl workspace coupling**: the API imports
  `patcher.core.installomator` for `parse_fragment` and `resolve`, which
  pulls in patcherctl's full runtime dep tree (including `keyring`,
  `pandas`, `fpdf2`). Linux deployments must set
  `KEYRING_BACKEND=keyring.backends.null.Keyring` to avoid keyring's
  Linux-without-DBUS import failure. Future cleanup: slim patcherctl's
  hard deps via optional extras (`[cli]`, `[reports]`).

## Documentation

User-facing docs are organized by audience-neutral topic under `docs/`:

- `docs/getting-started/`: install, configure Jamf, set up CLI / library
- `docs/usage/`: day-to-day commands and library calls (export, analyze, reset, automation)
- `docs/integrations/`: Installomator and other data-source integrations
- `docs/concepts/`: architecture, matching logic, local data storage
- `docs/api/`: the hosted Patcher API service (private beta)
- `docs/reference/`: auto-generated source-code reference (reStructuredText)
- `docs/contributing/`, `docs/faq.md`, `docs/troubleshooting.md`

Pages are Markdown via MyST except `docs/reference/` (RST). The Shibuya theme
is configured via captioned root toctrees in `docs/index.md`; each caption
becomes a section header in the sidebar. Build with `make docs`. The site
publishes to https://patcher.readthedocs.io.

When adding a new user-facing feature:
1. Add a page in the topic directory it belongs to (or extend an existing one).
2. Wire it into the appropriate captioned toctree in `docs/index.md`.
3. Add a `:::{rst-class} lead` block of 1–2 sentences just below the H1.
4. Run `make docs` and verify zero warnings before committing.

Reference docs (auto-generated) update on their own as long as docstrings
follow the conventions above.

## What's out of scope

- **Don't add new dependencies casually.** Patcher's surface area is
  intentionally focused. Discuss in an issue before introducing a new top-level
  dependency.
- **Don't introduce new credential storage backends** without discussion.
  Keychain (macOS) and in-memory (CI/CD) are the two supported paths.
- **Don't add features that require live Jamf access to be useful** without
  also providing a meaningful mock-based fallback path.

## Vendor docs

Upstream Installomator and AutoPkg wikis are included as git submodules under `vendor-docs/`:

- `vendor-docs/installomator/`: Installomator wiki (https://github.com/Installomator/Installomator/wiki)
- `vendor-docs/autopkg/`: AutoPkg wiki (https://github.com/autopkg/autopkg/wiki)

**When working on Installomator- or AutoPkg-related code, consult these local docs before fetching from the web.** They are the authoritative reference for label variables, recipe processors, and upstream behavior. Do NOT infer how something works from existing code alone; verify against the wiki pages.

Submodule state is pinned, so what you find reflects the version we've accepted. `make update-vendor-docs` bumps to upstream latest as a deliberate review action; `make init-vendor-docs` fills `vendor-docs/` for contributors who cloned without `--recursive`.

Common entry points:

- Installomator label variables: `vendor-docs/installomator/Label-Variables-Reference.md`
- Installomator `valuesfromarguments` mechanism: search the Installomator wiki
- AutoPkg recipe structure, processors, parent inheritance: `vendor-docs/autopkg/Home.md` and adjacent pages

## Where to look for more context

- `CHANGELOG.md`: release history
- `docs/`: Sphinx user docs (getting-started, usage, integrations, concepts, api, reference, contributing, faq, troubleshooting)
- `pyproject.toml`: dev dependencies, ruff config, pytest config
- `.pre-commit-config.yaml`: required hooks
- `.cursor/rules/`: additional style rules picked up by Cursor specifically
- `vendor-docs/`: upstream Installomator + AutoPkg wikis (git submodules)
