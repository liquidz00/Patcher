# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`patcherctl` is a macOS tool (Python 3.10+) that pulls patch-management data from the Jamf Pro API and produces Excel / PDF / HTML / JSON reports. Today it ships as a CLI; importable-package usage is **planned** — when adding code, treat the public import surface as something that's about to exist (clean module boundaries, no CLI-only assumptions baked into core logic), but don't yet stabilize an API contract.

## Commands

The project uses `uv` for dependency/venv management and a `Makefile` as the canonical task runner. Prefer `make` targets over invoking tools directly so flags stay consistent.

```
make install-dev           # uv sync --extra dev (creates .venv, installs docs deps too)
make test                  # pytest tests/ -v
make test-cov              # pytest with coverage to term + coverage/htmlcov
make lint                  # ruff format --check . && ruff check .
make format                # ruff format . && ruff check . --fix
make build                 # uv build (sdist + wheel)
make docs                  # sphinx-build -b html docs/ docs/_build/
```

Run a single test: `uv run pytest tests/test_setup.py::TestSetup::test_x -v`
Run by marker: `make test-unit`, `make test-integration`, `make test-fast` (markers: `unit`, `integration`, `slow`, `asyncio`).

CLI entry point during development: `uv run patcherctl ...` (script defined in `pyproject.toml` -> `patcher.cli:cli`).

## Architecture

The CLI is **async-first** — `cli/__init__.py` uses `asyncclick` and the entry point is `asyncio.run(cli())`. Treat every command callback as a coroutine.

### Dependency wiring

`cli/__init__.py` is the composition root. On every invocation it builds a context dict (`ctx.obj`) containing the long-lived collaborators that subcommands pull from:

- `ConfigManager` — credential storage. **Two modes**: keychain-backed (default, via `keyring`) or `in_memory_credentials` (set when `--client-id/--client-secret/--url` or `PATCHER_*` env vars are all present). The in-memory mode is the **non-interactive / CI mode** — it bypasses keychain and skips every prompt. Reads fall through memory → keyring; writes in memory mode never touch keyring.
- `PropertylistManager` — reads/writes `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist` for UI/branding settings.
- `UIConfigManager` — PDF header/footer, fonts, logo, header color.
- `Setup` — drives first-run flow as a linear sequence (prompt creds → create API role/client on Jamf side for Standard / save existing creds for SSO → fetch token → save `JamfCredentials` → prompt UI settings → mark complete). Completion tracked by the `setup_completed` plist boolean; `--fresh` re-runs regardless. Non-interactive runs go through `Setup.bootstrap_noninteractive` instead of `Setup.start`.
- `DataManager` — patch data caching, validation, export (Excel/PDF/HTML/JSON). Initialized **lazily** via `get_data_manager(ctx)`; cache disabled when `--disable-cache` is set. Cache lives at `~/Library/Caches/Patcher`.
- `Animation` — terminal spinner; commands run inside `animation.error_handling()` async context manager which translates exceptions into formatted CLI errors.

### Layered API client

`patcher.client.HTTPClient` (in `client/__init__.py`) is the foundation: it owns `asyncio.Semaphore`-bounded concurrency (default 5; **do not raise without cause** — Jamf scalability guidance), wraps a lazily-constructed `httpx.AsyncClient` exposed via the `http` property (TLS via `truststore.SSLContext` so OS-installed CAs are honored automatically), and centralizes HTTP status handling (4xx/5xx → `APIResponseError`, with a `not_found=True` flag for 404). The three async entry points are `fetch_json`, `fetch_text`, and `fetch_basic_token`; one-shot sync downloads (default fonts) use `httpx.get` directly with the same truststore context.

`patcher.client.JamfClient` (in `client/jamf.py`) extends `HTTPClient` with Jamf-specific endpoints. `TokenManager` (used inside `JamfClient`) handles bearer token lifecycle; `JamfClient._headers()` calls `TokenManager.ensure_valid_token()` on every request, so token validation happens once per call without a decorator wrapping methods. **Never instantiate `JamfClient` before setup completes** — its constructor calls `token_manager.attach_client()` which returns a `JamfCredentials` Pydantic model (the credentials container; renamed from the legacy `JamfClient` model in Phase 5).

### Directory layout

Source is organized into three layers under `src/patcher/`:

- **`client/`** — HTTP transport, no CLI/keyring deps. `HTTPClient` (in `client/__init__.py` — generic httpx plumbing), `JamfClient` (in `client/jamf.py` — Jamf-specific endpoints), `TokenManager`.
- **`core/`** — domain logic, managers, and the library facade. No `asyncclick` / `PIL` imports. `patcher_client` (the `PatcherClient` facade — headline library entry), `exceptions`, `logger` (stdlib only), `config_manager` (keyring lives here), `data_manager`, `pdf_report` (takes a UI config dict, falls back to Helvetica when font paths are absent), `report_manager` (helpers only — `process_reports` lives in `cli/`), `analyze`, `installomator` (accepts `api=` for DI), `fonts` (standalone `ensure_default_fonts(target_dir)`), and the Pydantic `models/` subpackage.
- **`cli/`** — CLI surface. `cli/__init__.py` is the click entry point and composition root; `cli/setup.py` holds the interactive setup flow and the UI prompts; `cli/report.py` holds `process_reports` (now takes a `PatcherClient`); `cli/plist_manager.py` is the plist persistence; `cli/ui_manager.py` is the plist-coupled UI config + interactive setup integration; `cli/animation.py` is the terminal spinner; `cli/terminal_logger.py` is the click-styled logging adapter installed when `--debug` runs.

The repo root also reserves an `api/` directory (sibling to `src/`) for the future Patcher API service — the canonical apps/patching-methods database. It is a separate deliverable and is **not** packaged into the Python distribution.

### Exit codes (defined in `cli/__init__.py` docstring)

`0` success · `1` `PatcherError` · `2` unhandled · `3` `SetupError` · `4` `APIResponseError` · `130` Ctrl+C. Custom exceptions inherit from `PatcherError` and carry context kwargs (e.g. `raise APIResponseError("...", status_code=..., url=...)`); the formatter renders them as `message (key1: val1 | key2: val2)`.

## Conventions

- **Docstrings: Sphinx/reST only** (`:param:`, `:type:`, `:return:`, `:rtype:`, `:raises:`). No Google/NumPy style. Opening `"""` on its own line, even for one-liners. See `.cursor/rules/sphinx-style-docstrings.mdc`.
- **Line length 100**, double quotes, ruff format + `ruff check`. Selected lint rules are narrow (`E101`, `F401`, `F403`, `I001`, `N801/802/806`); `E722` is intentionally ignored. Tests are exempt from `N806` because they assign mocks to PascalCase names (`MockTokenManager = MagicMock()`) — keep that pattern in new tests.
- **Async tests**: `pytest.ini_options` sets `asyncio_mode = "strict"` with function-scoped loops — every async test needs the `@pytest.mark.asyncio` marker.
- Coverage runs on every `pytest` invocation (configured in `pyproject.toml`'s `addopts`); HTML report lands in `coverage/htmlcov/`.
- Pre-commit hooks (ruff, file hygiene, validate-pyproject, etc.) run on commit. Install with `make pre-commit`.
- `__about__.py` holds `__version__` — `pyproject.toml` reads it dynamically. Bump there when releasing.
