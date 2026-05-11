# AGENTS.md

Instructions for AI coding agents working on Patcher. Tool-agnostic — applies
equally to Claude Code, Cursor, Aider, or any other coding assistant.

## What Patcher is

A Python CLI for MacAdmins that pulls patch management data from the Jamf Pro
API and exports reports in Excel, HTML, PDF, and JSON formats. Distributed as
the `patcherctl` command via PyPI (project name: `patcherctl`, package name:
`patcher`).

There is a separate but tracked goal of making the underlying logic importable
as a library so users can call into Patcher programmatically, not just via the
CLI. Keep this in mind when adding new features — prefer pure functions and
classes that can be used outside the Click context, and have the CLI be a thin
wrapper.

## Quick start

```bash
# Set up dev environment (uv handles the venv + deps)
uv sync --all-extras

# Run the CLI locally
uv run patcherctl --help

# Common make targets
make test     # pytest tests/
make lint     # ruff format --check + ruff check
make format   # ruff format (does NOT remove unused imports — use lint for that)
make docs     # sphinx-build -b html docs/ docs/_build/
```

Pre-commit hooks are configured (`.pre-commit-config.yaml`). They run on every
commit and must pass. Install once with `pre-commit install`.

## Project layout

```
src/patcher/
├── cli.py                    # asyncclick entry point — three subcommands: reset, export, analyze
├── client/
│   ├── api_client.py         # Pro API wrapper — uses ConfigManager for credentials
│   ├── config_manager.py     # Keychain (or in-memory) credential storage
│   ├── token_manager.py      # OAuth client_credentials flow, token lifecycle
│   ├── setup.py              # Interactive + non-interactive setup paths
│   ├── plist_manager.py      # Reads/writes ~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist
│   ├── ui_manager.py         # PDF header/footer/logo configuration
│   ├── analyze.py            # Analysis criteria + filter/trend logic
│   └── report_manager.py     # Orchestrates the export pipeline
├── models/                   # Pydantic 2 models
│   ├── patch.py              # PatchTitle, PatchDevice
│   ├── jamf_client.py        # JamfClient
│   ├── token.py              # AccessToken
│   ├── label.py              # Installomator labels
│   ├── ui.py                 # UI config schema
│   └── fragment.py
└── utils/
    ├── data_manager.py       # Caching, DataFrame mgmt, export(...) entrypoint, serialize_titles_to_dict()
    ├── pdf_report.py         # FPDF rendering
    ├── installomator.py      # Installomator label resolution
    ├── exceptions.py         # PatcherError + subclasses (CredentialError, SetupError, TokenError, APIResponseError)
    ├── decorators.py         # @check_token (validates token before API calls)
    └── logger.py             # PatcherLog, LogMe

tests/                        # pytest, flat layout, conftest.py with shared fixtures
docs/                         # Sphinx + MyST + pydata-sphinx-theme; user/, reference/, contributing/
```

## Conventions

### Code style
- **Ruff** for linting + formatting. `make lint` is the source of truth.
  `make format` only fixes formatting, not lint issues like unused imports.
- **Line length 100**, double quotes, target Python 3.10+.
- **Modern union syntax** (`str | None`, `dict | int`) — NOT `Optional[str]`,
  NOT `Union[str, int]`. The Cursor rule on this is out of date relative to
  the actual code; trust the code.
- **Sphinx/reST docstrings** for every public function, method, and class.
  Use `:param:`, `:type:`, `:return:`, `:rtype:`, `:raises:`. Do NOT use
  Google or NumPy docstring style. See `.cursor/rules/sphinx-style-docstrings.mdc`.
- **PEP 8 naming**: `snake_case` for funcs/vars, `PascalCase` for classes,
  `UPPER_CASE` for constants. PascalCase mock vars in `tests/` are exempt
  from `N806` (configured in `pyproject.toml`).
- **Type hints on everything** — params and return types, including for
  private methods.

### Async-first
Most of the codebase is async. CLI is built on `asyncclick`. New API-touching
code should be async. When you need to call sync code from async context, use
`asyncio.to_thread`.

### Pydantic 2
All models inherit from `BaseModel`. Serialize with `.model_dump(mode="json")`
when producing JSON output — preserves enum values, datetimes, and nested
structures correctly. `.model_dump()` (no mode) returns Python natives.

### Errors
Custom exceptions live in `utils/exceptions.py`. All inherit from `PatcherError`.
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
- Tests are in `tests/` — unit tests are flat at the top level; integration
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
  significant changes (e.g. transport migrations) — but they are NOT a
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
never touched. See `docs/user/ci_cd.md` for the user-facing contract.

When adding features, **don't break this**: avoid hardcoding paths to
`~/Library/Application Support/...` or assuming a macOS keychain backend
exists. Anything that needs credentials should go through `ConfigManager`,
which abstracts the storage backend.

## Things to be careful about

These are known rough spots. Don't refactor them as part of an unrelated PR;
file an issue and tackle separately.

- **`@check_token` decorator** (`utils/decorators.py`): adds a layer of
  indirection around token validation that's harder to follow than necessary.
  Likely simplifiable but coupled to many call sites.
- **Setup state machine** (`client/setup.py`): four named stages
  (`NOT_STARTED`, `API_CREATED`, `HAS_TOKEN`, `JAMFCLIENT_SAVED`, `COMPLETED`)
  with a JSON file persisting progress. More complex than the linear flow
  warrants. `bootstrap_noninteractive` deliberately bypasses it.
- **`ApiClient` / `BaseAPIClient` / `TokenManager` overlap**: responsibility
  boundaries are blurry. Consolidating would help, but high blast radius.
- **`DataManager` is large** (~570 lines): caching, validation, export,
  filename generation, DataFrame conversion all in one class. Splitting would
  help but is a noisy refactor.

## Documentation

User-facing docs live in `docs/user/` (Markdown via MyST) and `docs/reference/`
(reStructuredText, auto-generated from docstrings). Build with `make docs`.
The site publishes to https://patcher.readthedocs.io.

When adding a new user-facing feature:
1. Update or add a page under `docs/user/`.
2. Wire it into the appropriate toctree in `docs/user/index.md`.
3. Run `make docs` and verify zero warnings before committing.

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

## Where to look for more context

- `CHANGELOG.md` — release history
- `docs/user/` — user guide
- `docs/contributing/` — contribution guide (if present)
- `pyproject.toml` — dev dependencies, ruff config, pytest config
- `.pre-commit-config.yaml` — required hooks
- `.cursor/rules/` — additional style rules picked up by Cursor specifically
