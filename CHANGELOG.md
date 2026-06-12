<!-- markdownlint-capture -->
<!-- markdownlint-disable -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **`PatcherClient.analyze(..., where=)`** accepts a `min_compliance` / `min_hosts` / `released_after` pre-filter, matching the CLI's `analyze` filters.
- **Catalog `App` records now expose `expected_team_id`.** The Apple Team ID (used for code-signature verification, authoritatively sourced from Installomator) is promoted onto the stitched app record, so `GET /apps` and `GET /apps/{slug}` carry it directly instead of requiring a second `/apps/{slug}/sources` lookup.

### Changed
- **The `/apps*` ETag is now a version token instead of a file hash, and `/stats` renames `catalog_sha` to `catalog_version`.** The catalog cache key was the SHA-256 of the whole SQLite file (a ~1s, 65 MB read plus a WAL checkpoint on every macOS-resolver upload); it's now the catalog's newest update timestamp, which moves exactly when the served data does. The `/stats` content field that exposes this value is renamed `catalog_sha` → `catalog_version` to match (its value is now a timestamp-derived token, not a hash). ETag/`If-None-Match` revalidation behavior is otherwise unchanged.
- **Patcher no longer keeps a local Installomator label cache.** The on-disk `~/Library/Application Support/Patcher/.labels` cache (unbounded, never expired) is gone; label fetches now go straight to the catalog. Any leftover directory is removed automatically on the next run and by `reset cache`.
- **Internal: report rendering split out of `DataManager` into a new `Exporter`.** `DataManager` now owns only the on-disk cache and DataFrame (de)serialization; PDF/Excel/HTML/JSON rendering moved to `patcher.core.exporter.Exporter`. The public `PatcherClient.export(...)` API is unchanged. Library callers using `DataManager.export(...)` or the module-level `serialize_titles_to_dict` directly should switch to `PatcherClient.export(...)` or `Exporter`.
- **Internal: the `analyze` CLI command routes through `PatcherClient`** (`analyze` / `analyze_trend` / `export`) instead of reimplementing the `TitleFilter` / `TrendAnalysis` transforms inline. No change to `analyze` behavior or output.
- **Internal: `PatchTitle ↔ DataFrame ↔ dict` conversions consolidated into a new `patcher.core.serialization` module** (`titles_to_df` / `df_to_titles` / `titles_to_dict`). `DataManager`, `Exporter`, and the trend-analysis diff path now share these instead of each re-implementing `model_dump`. `Exporter.serialize_titles_to_dict(...)` is unchanged and now delegates to `titles_to_dict`.
- **Internal: release-date formatting and the SOFA feed moved off `JamfClient`.** Display formatting (`Aug 09 2023`) is now a `PatchTitle.released` field validator instead of the private `JamfClient._convert_tz`, and the SOFA fetch is a `patcher.core.analyze.get_sofa_feed(http_client)` function rather than a `JamfClient` method. No change to export output.
- **Internal: the trend-diff path reuses the shared serialization helper.** `Diff` now hydrates DataFrame rows into `PatchTitle` objects via `patcher.core.serialization.df_to_titles` instead of a bespoke row-by-row reimplementation.
- **Internal (API): mock seed data no longer auto-loads on startup.** `seed_on_startup` now defaults to `False`, so a fresh self-hosted catalog stays empty until ingest runs (set `PATCHER_API_SEED_ON_STARTUP=true` or run the seed module explicitly for dev).
- **Internal: catalog wire schemas now have a single definition.** `App`, `AppSources`, the per-source payloads, the generated-label, and drift schemas live in `patcher.catalog.schemas` and are shared by the library client and the API server, replacing two hand-mirrored copies that had drifted. They remain importable from `patcher.clients.patcher_api` for backwards compatibility.
- **Internal: the Installomator fragment parser now has a single definition.** `parse_fragment` (and its quote-aware scanner) lives in `patcher.catalog._fragment_parser`, shared by the library's `InstallomatorClient` and the API ingest, replacing a duplicated copy that lived in each.
- **Internal: app-name normalization is now a single shared function.** The library matcher and the API catalog stitch share `patcher.catalog._normalize.normalize_name` instead of two separate, drifted implementations. The library's matcher now strips all non-alphanumeric characters (matching the API), so punctuated app names normalize more consistently.
- **Internal: HTTP requests funnel through one primitive.** Every client call (`fetch_text`, `fetch_json`, `fetch_batch`, and the Jamf basic-token POST) now routes through a single `HTTPClient._request` (semaphore + network-error translation) and a single `_raise_for_status` (errors/detail unification, 404 handling), replacing per-method copies of the same try/except. A 404 now raises the new `NotFoundError` (a subclass of `APIResponseError`, still carrying `not_found=True`), so callers can `except NotFoundError` for the not-found case while existing `except APIResponseError` handlers keep working.
- **Internal (API): the catalog stitch's two phases share one resolver and one commit path.** The Installomator-led and Cask-only phases were near-duplicate ~80-line blocks (index lookups, source-list assembly, field/payload resolution, nested-transaction upsert, counter bookkeeping). They now share a `_match_aux` resolver, per-primary `_resolve_label`/`_resolve_cask` builders, and a single `_commit_app`; the five lookups are grouped into a `_StitchIndexes`. No change to the stitched output or the returned counts.

### Deprecated
- **`InstallomatorClient` is deprecated** and will be removed in a future release; constructing it now emits a `DeprecationWarning`. Use `PatcherClient` / `PatcherAPIClient` for label and match data (set `PATCHER_API_URL` for self-hosted catalogs).

### Removed
- **The always-null `latest_release_date` field was removed from catalog `App` records.** It was never populated in production (only by seed mock data), so it's gone from `/apps` responses and the `App` model; a migration drops the `apps.latest_release_date` column.
- **The Mac App Store (MAS) catalog source was removed.** It was a dormant source (Apple's ~20 req/hr lookup rate-limit made it impractical, and it carried no `download_url` and little cross-source overlap). `mas` no longer appears in any app's `sources`, the `mas` per-source payload is gone from `GET /apps/{slug}/sources`, and the `MasSource` client model was removed. A migration drops the `mas_apps` table and the `app_source_details.mas` column.
- **`DataManager.load_cached_data` and `HTTPClient.set_concurrency` were removed.** Both were unused: `load_cached_data` had no callers, and outbound concurrency is set once at construction via the `max_concurrency` argument.

### Fixed
- **`analyze --excel-file` (and `PatcherClient.analyze_excel`) now actually read the file.** Previously the path was accepted but ignored, and analysis ran against the cached snapshot instead. You can now analyze a previously-exported Excel report directly — useful for re-analyzing a shared or historical export without re-fetching from Jamf. Combining `--excel-file` with `--all-time` is rejected with a clear error.
- **Matched Installomator labels in reports now carry their install type, download URL, and Team ID.** Previously every `install_label` entry in an export showed `null` for `type`, `download_url`, and `expected_team_id` even when the catalog had them; the matcher now hydrates all three from the matched catalog record.
- **The `installomator` analyze filter no longer counts uncovered titles.** A title with no Installomator label could slip through the filter (it compared against an empty list, not truthiness), so titles without a label were wrongly listed as Installomator-covered.
- **Fetching an app's per-source detail no longer crashes on shared AutoPkg recipes.** `PatcherAPIClient.get_app_sources` raised a validation error for any app whose matched AutoPkg recipes had a `null` name or shortname (shared-processor recipes); the client model now matches the API and tolerates them.
- **A malformed token response surfaces a clear error.** If the Jamf API returned a success response missing the `access_token` or `expires_in` field, Patcher raised an unhandled `TypeError`; it now raises a `TokenError` explaining the response was incomplete.
- **Resetting credentials in in-memory mode no longer touches the system keychain.** `ConfigManager.delete_credential` ignored in-memory mode and always called keyring; it now removes from the in-memory store, matching `get_credential`/`set_credential`.
- **Cache pruning no longer stops at the first undeletable file.** When clearing expired snapshots, a single locked or permission-denied file aborted the whole cleanup; it now logs the file and continues pruning the rest.
- **Jamf App Installer source detail now exposes its full fields.** `get_app_sources(...).jamf_app_installer` previously kept only `title`/`source`/`host` and silently dropped `bundle_id`, `version`, `jamf_id`, `download_url`, and `architecture` that the API returns; the client now captures them.


## [v3.3.1] - 2026-06-09
### Fixed
- **Cached snapshots survive pandas upgrades.** Patch-data snapshots are cached in [Parquet](https://parquet.apache.org/) format to prevent `TypeError`'s after pandas version changes. Existing pickle ccaches are still read where the installed pandas can load them ([#81](https://github.com/liquidz00/Patcher/issues/81)).
- **All errors render in styled panels.** All errors are rendered consistently instead of `PatcherError` objects only ([#81](https://github.com/liquidz00/Patcher/issues/81)).

## [v3.3.0] - 2026-06-09
### Added
- **`GET /stats` API endpoint.** One call returns catalog size, per-source coverage counts, the content hash, and the last-refresh timestamp.
- **Configurable matching skip list.** Skip your own Jamf-title patterns (`fnmatch` syntax) via the `ignored_titles` plist key or `PatcherClient(ignored_titles=[...])`. They will merge with the built-in defaults (Adobe, Jamf, etc.).
- **Fuller Jamf catalog matching.** Patcher now ingests every Jamf Patch Management title (not just the App Installers subset), so more of your patch titles resolve to an Installomator label or Homebrew coverage before any fuzzy matching runs.

### Changed
- **The CLI output got a Rich overhaul.** `analyze`, `diff`, and `drift` render styled tables; `analyze` leads with a fleet-compliance panel and color-codes each title's completion (red/yellow/green by `--threshold`) with row dividers; `export` shows a live progress bar with a running title count and ETA; the first-run setup welcome is a bordered panel; and errors appear in a red panel with recovery hints.
- **Setup offers matching across all sources.** The first-run prompt now reads "Would you like to enable matching (Installomator, Homebrew)?" and turns on both sources (previously Installomator only).
- **More titles match out of the box.** A curated seed backfills bundle IDs for ~two dozen apps (Zoom, Docker, OBS Studio, DBeaver, and more) so cross-source matching and drift detection work for them, and matching now skips Adobe- and Jamf-published titles by default (managed out-of-band) to keep `analyze` reports actionable.
- **Configuration consolidated into one model.** Every on-disk setting now lives in a single `PatcherSettings` plist model; older plist formats migrate automatically on first launch (keeping a `.bak` copy), no user action required.

### Fixed
- **Setup and `reset` no longer hang at the first prompt.** A live status spinner held the terminal across the interactive prompts so keystrokes never registered which blocked every new user and anyone running `patcherctl --fresh`, `reset full`, `reset creds`, or `reset ui`.
- **The API Client Secret is now hidden during entry.** It previously echoed in plaintext during SSO setup and `reset creds`, it is now masked like the Jamf Pro password.
- **Errors always render in the styled panel.** Launched via the `patcherctl` command (not just `python -m patcher.cli`), `PatcherError`s now show the bordered red panel with its recovery hint and log-file pointer instead of a plain one-line message.
- **Closing a `JamfClient` or `PatcherClient` releases every connection pool.** The internal token manager leaked one HTTP pool per client; `aclose()` (and `async with`) now close it too.

### Deprecated
- **`PatcherClient(enable_installomator=...)` is renamed to `enable_matching`.** The old keyword still works but emits a `DeprecationWarning`; update library calls to `enable_matching=`.

## [v3.2.0] - 2026-06-03
### Added
- **MCP server for the Patcher catalog.** Point Claude or any Streamable HTTP MCP client at the catalog and ask about it in natural language, with no `curl` or API client required. Eight read-only tools cover catalog summaries, app lookups, search, version drift, categories, Installomator label generation, per-source data, and recent additions, alongside pinnable catalog resources and ready-made prompts. Live at `mcp.patcherctl.dev`, or self-hosted at `/mcp`.
- **Self-hosting for the Patcher API.** A reference `Dockerfile` and `docker-compose.yml` ship at the repo root with a [self-hosting guide](https://docs.patcherctl.dev/en/latest/project/self-hosting.html), so you can run your own catalog mirror. Community-supported, with the public `api.patcherctl.dev` still running on systemd.
- **New filters and trends for `analyze`.** Impact-weighted risk ranking (missing patches weighed against days since release), coverage-gap detection (titles with neither an Installomator label nor a Homebrew match), chainable `--min-compliance` / `--min-hosts` / `--released-after` pre-filters, average time-to-patch, and stale-app detection across snapshots.

### Changed
- **CLI output now renders through [Rich](https://github.com/Textualize/rich).** Status messages, warnings, errors, tables, and spinners share one consistent style, errors appear in a bordered panel with recovery hints, and tracebacks hide local variables so pasted output never leaks credentials.

### Removed
- Removed the unused `cves` field from the `App` model and from API, MCP, and package-client responses. It was reserved but never populated, and Patcher stays focused on patch reporting and analysis rather than vulnerability intelligence. Drop any references to `app["cves"]`.

## [v3.1.1] - 2026-05-30
### Fixed
- PDF reports now honor configured plist UI settings ([#69](https://github.com/liquidz00/Patcher/issues/69)).
- Python interpreter mismatch on Keychain writes now surfaces a recoverable error ([#68](https://github.com/liquidz00/Patcher/issues/68)).
- `patcherctl --fresh` now actually re-triggers setup ([#70](https://github.com/liquidz00/Patcher/issues/70)).
- `asyncclick>=8.2.2` enforced as the minimum ([#72](https://github.com/liquidz00/Patcher/issues/72)).
- `ctx.exit(0)` replaced with `sys.exit(0)` across the CLI ([#73](https://github.com/liquidz00/Patcher/issues/73)).

## [v3.1.0] - 2026-05-28
### Added
- Jamf App Installers per-title metadata now includes bundle ID, version, and download URL (previously only title, source, and host).
- More Installomator labels now resolve their dynamic `downloadURL` / `appNewVersion` values, including ones that previously required macOS-only evaluation.
- `patcherctl diff` subcommand for snapshot comparison, with `--since`, `--all-time`, `--between`, `--list-snapshots`, and `--format json`. Available at the library level as `PatcherClient.diff()`.
- `patcherctl drift` subcommand for surfacing apps where Installomator and Homebrew Cask disagree on the current version. Available at the library level as `PatcherClient.detect_drift()` and at the API level via `GET /apps/drift` and `GET /apps/{slug}/drift`.
- Homebrew Cask as a second matching dimension for patch reports via `patcherctl export --homebrew`. Off by default.

### Fixed
- Installomator label parser no longer truncates or collapses shell-expression values ([#65](https://github.com/liquidz00/Patcher/issues/65)).
- `GET /apps/{slug}/sources` now correctly returns `jamf_app_installer` coverage (previously fell back to `null` for every app).
- `GET /apps/{slug}/sources` no longer returns 500 for apps whose AutoPkg recipes have a `null` `name` or `shortname`.
- Jamf App Installers now matches catalog titles that carry a vendor prefix or a version / edition suffix (e.g. `SAP Privileges` → `privileges`, `Sublime Text 4` → `sublimetext`).
- Resolved `appNewVersion` values are sanity-checked before storage, preventing HTML pages or multi-line output from being stored as versions.

## [v3.0.0] - 2026-05-21
### Added
- **`PatcherClient`**, the new headline library entry point. Composes `JamfClient`, `PatcherAPIClient`, and `DataManager`, supports `async with` cleanup via `aclose()`, and exposes `fetch_patches`, `analyze`, `analyze_excel`, `analyze_trend`, and `export` as one-call shortcuts.
- **`PatcherClient.from_state()`** classmethod for callers running on a Mac that already completed `patcherctl` setup. Reads credentials from Keychain, UI config from the property list, and the Installomator toggle.
- **Hosted Patcher API service at `https://api.patcherctl.dev`** with a stitched catalog of macOS app patching metadata from Installomator, Homebrew Cask, AutoPkg, Mac App Store, and Jamf App Installers. Endpoints + worked examples documented at [docs.patcherctl.dev](https://docs.patcherctl.dev/en/latest/reference/api/endpoints.html).
- **`PatcherAPIClient`** as the typed Python wrapper over `api.patcherctl.dev`. Returns Pydantic `App` / `AppSources` / `GeneratedLabel` models for list, filter, per-source, and label-generation reads.
- **`TitleFilter` and `TrendAnalysis` classes** replace the `FilterCriteria` / `TrendCriteria` enums. Each former enum value is a method (`TitleFilter(titles).most_installed(top_n=10)`, `TrendAnalysis(datasets).patch_adoption()`) with its own signature. The CLI's `--criteria` strings and `PatcherClient.analyze("most-installed", ...)` continue to work via new `TitleFilter.apply` / `TrendAnalysis.apply` dispatch helpers.
- **TLS via the OS native trust store** (`truststore` dependency). Corporate CAs installed at the OS level (macOS Keychain, Windows Cert Store, Linux `/etc/ssl/certs/`) are trusted automatically; TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, GlobalProtect) work with no per-application configuration.
- **Auto-configured null keyring backend on non-macOS platforms.** Linux runners, Linux servers, Docker containers, and Windows hosts no longer need `KEYRING_BACKEND=keyring.backends.null.Keyring` set by hand. An explicit env var still wins. macOS behavior unchanged.
- **Integration test scaffolding** under `tests/integration/`. Opt-in via `make test-integration`. Defaults to Jamf's published dummy instance; override with `PATCHER_INTEGRATION_URL` / `PATCHER_INTEGRATION_CLIENT_ID` / `PATCHER_INTEGRATION_CLIENT_SECRET`.
- **Bundled Claude Code skill** at `.claude/skills/patcher/`: a read-only lookup utility that surfaces Installomator, Homebrew Cask, AutoPkg, and Jamf App Installer coverage for any Mac app, in one slash command.
- Documentation moved to a custom domain at [docs.patcherctl.dev](https://docs.patcherctl.dev), reorganized around audience-neutral topics, and migrated to the [Shibuya theme](https://shibuya.lepture.com).
- GitHub issue templates migrated to YAML forms (`bug_report.yml`, `feature_request.yml`, `feedback.yml`).

### Changed
- **Source layout split into `clients/`, `core/`, and `cli/` packages.** Old imports from `patcher.utils.*` and `patcher.models.*` are gone; update to `patcher.core.*` and `patcher.core.models.*`.
- **`BaseAPIClient` → `HTTPClient`** (generic httpx-with-truststore base) and **`ApiClient` → `JamfClient`** (Jamf-specific HTTP client). Sets the per-service-client naming pattern.
- **Pydantic `JamfClient` model → `JamfCredentials`.** Resolves the name collision with the HTTP client. Update `from patcher.core.models.jamf import JamfClient` to `JamfCredentials`. Top-level `from patcher import JamfClient` is unchanged and still refers to the HTTP client.
- **`Installomator` → `InstallomatorClient`.** User-facing docs and prose continue to refer to the upstream Installomator project; only the class name changed.
- **HTTP transport migrated from curl-subprocess to httpx** across the entire codebase. No more subprocess forks per request, connection pooling between calls, and credential redaction is no longer needed because httpx never serializes secrets into argv. Public exception contracts (`APIResponseError`, `not_found=True` on 404) preserved.
- **`InstallomatorClient` no longer requires Jamf credentials for label-only operations.** Use `InstallomatorClient().list_available_labels()` / `get_label()` standalone without any Jamf auth.
- **Public package facade slimmed.** `PatcherClient` is the headline. Still re-exported at top level: `JamfClient`, `InstallomatorClient`, `PatcherAPIClient`, `PatchTitle`, `PatchDevice`, `TitleFilter`, `TrendAnalysis`, and the exception classes. CLI-only objects (`Setup`, `UIConfigManager`, `Animation`, `PropertylistManager`) are deliberately not re-exported.
- **`PropertylistManager` and `UIConfigManager` moved from `core/` to `cli/`** (CLI-only concerns). `PDFReport` now accepts a plain `ui_config: dict` so library callers can generate PDFs without the plist-backed CLI surface.
- **Logger split.** `core/logger.py` is now stdlib-only. Click-styled console output lives in `cli/terminal_logger.py` and is installed only by the CLI entry point, so `import patcher` no longer mutates `sys.excepthook` or the warnings filter as a side effect.
- **`Setup.SetupStage` state machine removed** in favor of a linear `Setup.start()` flow. The single `setup_completed` plist boolean replaces the 5-stage progress file. `--fresh` still re-runs setup.
- **`ReportManager` class removed.** Its helpers became module-level functions in `patcher.core.analyze`: `sort_titles`, `omit_recent`, `append_ios_status`, `calculate_ios_on_latest`.
- **`Setup.prompt_*` methods are now `async def`** to support `asyncclick` 8.2+. The previous recursive retry on invalid input is replaced with a bounded loop. Resolves [#58](https://github.com/liquidz00/Patcher/issues/58) — `RecursionError` during setup on Python 3.14.
- **`InstallomatorWarning` now actually fires** when unmatched titles remain after matching. The CLI surfaces it via `warnings.simplefilter("always", InstallomatorWarning)`; library callers can catch it or suppress with `filterwarnings`.
- Project version bumped to `3.0.0`.

### Deprecated
- The legacy `patcher.utils.*` and `patcher.models.*` import paths. The directories no longer exist; update imports to `patcher.core.*`.

### Removed
- **`FilterCriteria` and `TrendCriteria` enums, the `Analyzer` dispatch wrapper, and `BaseEnum.from_cli`.** Replaced by `TitleFilter` and `TrendAnalysis` classes (see Added). Callers using `FilterCriteria.MOST_INSTALLED` or `TrendCriteria.PATCH_ADOPTION` directly will hit `ImportError`; either switch to the new classes or pass the kebab-case string form to `PatcherClient.analyze`.
- **`InstallomatorClient.match` and its helpers** (`_match_directly`, `_match_fuzzy`, `_second_pass`, `_save_unmatched_apps`, `_normalize`, `_parse`). The canonical matcher is now `patcher.core.matching.match_titles`, which `PatcherClient.fetch_patches` runs internally. Callers using `.match()` directly should switch to `PatcherClient.fetch_patches`.
- **`patcher.core.models.fragment.Fragment` Pydantic model** and its reference page. Unused scaffolding with no callers.
- **`ReportManager` class** (see Changed for the migration path).
- **`Setup.SetupStage` state machine** (see Changed).
- **`check_token` decorator** (`client/decorators.py`). Token validation was running twice per request; the `ValidationError → TokenError` conversion moved into `ensure_valid_token()` itself.
- **Legacy curl-subprocess transport** (`BaseAPIClient.execute`, `execute_sync`, `_sanitize_command`, `_format_headers`). `subprocess` and `asyncio.create_subprocess_exec` are no longer imported anywhere.
- `ShellCommandError` exception class (no remaining raisers).

### Fixed
- **CLI setup flow's credential-persistence step now runs end-to-end.** Previously `Setup.start()` tried to instantiate the HTTP client `JamfClient` where it meant the Pydantic `JamfCredentials` model; a `NameError` fired before persistence. The mock-`start()`-entirely test pattern hid the bug.
- **`PatcherClient.export` now reads the configured `header_text`** from `ui_config` (was looking up the legacy uppercase key, silently rendering the default `"Patch Report"` header).
- **Patcher API URL validation** on ingested values, so resolved pipeline output that isn't a clean `http(s)://` URL no longer slips into `download_url` columns and breaks response serialization downstream.
- **AutoPkg ingest log noise quieted.** ~1000 Pydantic-validation warnings from malformed upstream records are aggregated into a handful of one-line summaries.
- **MAS slug collisions in stitch now merge** instead of silently dropping the MAS payload for popular apps (Microsoft Office, Apple Pro Suite).
- **`PatcherError` instance attributes restored.** `err.not_found`, `err.status_code`, etc. are now set from constructor kwargs, fixing the intended 404 short-circuit in matching.
- **Sphinx builds no longer fail under RTD's `-W` flag** because of the parallel-read/write annotation on custom extensions.

### Security
- **`JamfCredentials.client_secret` and `AccessToken.token` are `pydantic.SecretStr`.** Accidental serialization through `repr`, `model_dump`, `str()`, or unhandled exception tracebacks renders the masked placeholder instead of the secret. Callers needing the plaintext (OAuth request body, `Authorization` header, keychain write) call `.get_secret_value()` explicitly.
- **Pydantic `ValidationError` strings scrubbed before logging.** Previously the default `__str__` would surface offending field values (potentially including `client_id` / `client_secret` / `token` fragments) into log files. Both `TokenManager.attach_client` and `TokenManager.ensure_valid_token` now log field names only.
- **Jamf server URL forced to `https://`.** Inputs starting with `http://` are silently upgraded so bearer tokens never ship over plain HTTP.
- **Deploy tokens on `api.patcherctl.dev` now carry an `expires_at` column** (90-day default). Existing tokens with `expires_at = NULL` continue to work; rotate when convenient.
- **Rate limit on `/admin/*` routes** at 12 requests/hour/IP via `slowapi`. Catalog refresh CI run + occasional manual retries fit; a leaked deploy token can't run a brute-force loop. `/apps*` reads and `/health` stay unlimited (Cloudflare-edge rate-limited).
- **`If-None-Match` header parsing now handles RFC 7232 multi-value lists and the wildcard.** Clients sending `If-None-Match: W/"a", W/"b"` or `*` now get the intended 304 short-circuit instead of always receiving a full body.

## [v2.4.1] - 2026-05-12
### Fixed
- **`RecursionError` during setup on Python 3.14 / asyncclick 8.2+** ([#58](https://github.com/liquidz00/Patcher/issues/58)). `click.prompt` became an `async def` in asyncclick 8.2; calling it without `await` returns an un-awaited coroutine that never matches the expected setup-type choice, falls into the "Invalid choice" branch, and recursively re-invokes `Setup.start()` until the Python stack is exhausted. Every `click.prompt` call site in `Setup`, `UIConfigManager`, and the `reset` command now uses `await`. `Setup.prompt_credentials`, `UIConfigManager.setup_ui`/`configure_font`/`configure_logo` are now `async def` to support the awaitable prompts. The invalid-choice path in `Setup.start()` is also refactored from recursive retry to a `while True` loop so the same recursion footgun can't recur from any future input-validation regression.

## [v2.4.0] - 2026-05-04
### Added
- JSON output format for exported patch reports (`--format=json`). Suitable for machine-consumable pipelines and downstream automation.
- Non-interactive setup mode for CI/CD environments. Pass `--client-id` / `--client-secret` / `--url` (or `PATCHER_CLIENT_ID` / `PATCHER_CLIENT_SECRET` / `PATCHER_URL` env vars) to skip every interactive prompt and run without keychain access.
- Documentation page covering non-interactive mode with a complete GitHub Actions workflow example.


## [v2.3.0] - 2025-11-19
### Added
- Ability to customize the header color in exported HTML reports [(#39)(https://github.com/liquidz00/Patcher/issues/39)]
- Export patch reporting details 'per-app' using the `--device-details` or `-D` argument [(#35)(https://github.com/liquidz00/Patcher/issues/35)]


## [v2.2.0] - 2025-05-31
### Added
- Setup assistant tracks completion progress to prevent redundancy and `400` errors ([#29](https://github.com/liquidz00/Patcher/issues/29))
- Setup can be forcibly restarted by passing the `--fresh` argument, regardless of previous completion

### Changed
- Greeting is only shown if setup is in initial state to prevent redundancy. ([Docs](https://patcher.readthedocs.io/getting-started/setup/cli.html#starting-fresh))

## [v2.1.3] - 2025-03-16
### Changed
- Warnings about skipped Installomator labels are logged instead of being shown directly to stdout

### Fixed
- An issue causing the HTML template directory to not be included in built distribution

## [v2.1.2] - 2025-03-14
### Changed
- Problematic Installomator labels are now handled gracefully instead of raising exceptions ([#28](https://github.com/liquidz00/Patcher/issues/28))
- PDF classes have been refactored to resolve FPDF Deprecation warnings around `ln=True` usage

### Fixed
- An issue with HTML template path reference ([#27](https://github.com/liquidz00/Patcher/issues/27))
- CLI entry point references the correct property list value for HTML report titles

## [v2.1.1] - 2025-03-13
### Added
- Installomator support can be disabled should it not align with the security standards of your environment ([Docs](https://patcher.readthedocs.io/integrations/installomator.html#disabling-installomator-support))

### Changed
- Property list structure has been reformatted for simplicity and efficiency. ([Docs](https://patcher.readthedocs.io/concepts/data-storage.html))
- All property list methods refactored into own `PropertyListManager` class for separation of concerns

### Fixed
- An issue with bold fonts not be adding properly, leading to unhandled FPDF exceptions
- `404` status responses are properly handled during app matching process instead of raising an `APIResponseError` ([#26](https://github.com/liquidz00/Patcher/issues/26))
- Prevent inaccurate setup runs by checking property list migration before setup completion

## [v2.1.0] - 2025-02-15
### Added
- Export command defaults to exporting to all file formats (Excel, PDF, and HTML), with the `--format` option allowing for export of specific formats if desired
- [Installomator](https://github.com/Installomator/Installomator) matching. `PatchTitle` objects are matched with Installomator labels upon export
- Installomator `FilterCriteria` to show which labels are supported by Installomator

### Changed
- Added hour and minute information to cached data timestamp, allowing for caching of multiple reports in same day

### Fixed
- An issue where `date_format` was not being properly formatted as a datetime object in exported HTML reports
- `OSError` and `PermissionError` types are properly handled when trying to create directories
- `app_names` key returns a list of `appName` strings instead of first entry only
- An issue where `ReportManager` objects were not properly awaiting async functions

## [v2.0.3] - 2025-02-05
### Fixed
- Data sets are cached before dropping ignored columns so that analysis can complete as expected

## [v2.0.2] - 2025-02-02
### Added
- Support for tracking `softwareTitleId` from Jamf API Response
- macOS badge to README.md

### Changed
- Ignored columns are formatted properly before being dropped from export
- `title_id` attribute  is set to `"iOS"` when calculating amount of devices on latest version

### Fixed
- HTML template path references [#25](https://github.com/liquidz00/Patcher/issues/25)

## [v2.0.1] - 2025-01-24
### Fixed
- Resolved an issue where the entry point in `pyproject.toml` was not updated, preventing proper execution
- All changes from v2.0.0 are included in this release

## [v2.0.0] - 2025-01-23 [YANKED]
> **This release was yanked from PyPi due to an incorrect entry point configuration in the projects TOML file. This issue was fixed in v2.0.1.**

### Added
- Generated analyze summary file is now exported as an HTML report instead of a `.txt` file
- Title, header, and date format are dynamically set in HTML reports
- Support for data caching and resetting any cached data present
- `execute_sync` method to support synchronous API calls to prevent race conditions
- `Analyzer` class for analyzing collected patch management data based upon specified criteria
- Minimal viable product (MVP) class to begin [Installomator](https://github.com/Installomator/Installomator) support
- New export format support now leverages the `DataManager` class with automatic caching functionality

### Changed
- `ExcelReport` class refactored into `DataManager` class to support automatic caching
- `excel_file` parameter is no longer *required*, `DataManager` objects will default to latest cached dataset available
- `INFO`, `DEBUG`, and `WARNING` log level messages now have consistent format

### Deprecated
- `AccessToken` management has been refactored into `TokenManager`, deprecating `headers` property

### Fixed
- An issue where the default UI configuration was being overwritten mistakenly
- An issue with the `reset` method improperly returning `False` on successful resets
- An issue where stale `AccessToken` objects were being retrieved, leading to unauthorized API calls
- Refactored `None` to `""` when handling property lists to prevent `plistlib` errors

## [v1.4.1] - 2024-11-07
### Added
- `BaseAPIClient` class which allows for async `curl` calls as a workaround for SSL issues
- `SetupError` exception class to raise instead of returning `None`

### Changed
- `BaseAPIClient` class is utilized for API operations
- Max concurrency handling moved to `BaseAPIClient`
- Support both `GET` and `POST` requests in API calls
- API Role and API Client creation workflow leverages `fetch_json` method for improved HTTP error handling
- Credentials are lazy-loaded when needed instead of during init to prevent premature validation errors
- `ApiClient` and `TokenManager` objects are instantiated after completion of `Setup`
- Scope of `Setup` class has been narrowed, moving out-of-scope methods to proper classes

### Removed
- `APIPrivilegeError` exception

### Fixed
- Default header handling in API requests
- Calls for setting concurrency level
- Async handling during initialization

## [v1.4.0] - 2024-08-09
### Added
- Custom CA file path functionality to `UIConfigManager` class
- SSL verification checks that allow users to append a certificate path to the default CA file
- `pathlib.Path` objects for cross-platform functionality
- Latest version column added to datasets for exporting [#21](https://github.com/liquidz00/Patcher/issues/21)
- Support for logo file to be passed to use on generated PDF reports [#22](https://github.com/liquidz00/Patcher/issues/22)

### Changed
- Completion percent calculation is handled by `PatchTitle` class
- Prompt for setup method at runtime

### Removed
- `Delete` privileges from `ApiRole` model class
- Redundant calls to `click.Abort()`

### Fixed
- Animation class raises the exception that was caught
- Ensure tracebacks are written to log instead of `stderr`

## [v1.3.4] - 2024-07-29
### Added
- `--reset` flag to trigger setup assistant manually
- `format` and `clean` options to Makefile
- Functionality to delete stored credentials and `JamfClient` objects

### Changed
- Check for setup completion before executing `--reset`
- Logger objects are tied to specific class instances (child loggers)
- `LogMe` class creates child loggers during init

### Fixed
- `--omit` and `--sort` flags leverage `PatchTitle` class
- Sorting handles AttributeErrors gracefully
- Logger references fixed throughout

## [v1.3.3] - 2024-07-06
### Added
- Reference for report customization
- Additional static badges to README.md
- Functionality to publish to TestPyPI on pushes to `develop` branch

### Fixed
- Dynamic versioning during builds
- Relative import statements for package

## [v1.3.2] - 2024-07-05
### Added
- Functionality to dynamically create `config.ini` file on first launch
- `JamfClient` class, and URL validation function
- `cred_check` wrapper to ensure credentials are present when invoking CLI
- `PlistError` class to custom exceptions for error handling
- `asyncclick` library for asynchronous support

### Changed
- Project structure; leverage `src/patcher` directory and refactor references
- iOS version data calculation is handled by the `ReportManager` class
- First run wrapper includes welcome messaging by default
- Time zone conversion method moved to static method
- `ConfigManager` class leverages `keyring` library for environment variable handling
- Max concurrency defaults to 5 connections per Jamf API [scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices#rate-limiting)

### Removed
- `.env` and `ui_config.py` usage in favor of `keyring` and `config.ini`
- All references to `.env` file

### Fixed
- `ConfigManager` instance return values
- Incorrect log directory path references

## [v1.3.1] - 2024-06-22
### Added
- `--debug` (or `-x`) flag to view debug logs in `stdout` instead of default Animation
- Token expiration to `globals.py`

### Removed
- `threading.Event` from `LogMe` class configuration

## [v1.3.0] - 2024-06-18
### Added
- API Privilege error class
- Custom exceptions for error handling
- Functionality to calculate the amount of devices on the latest version of their respective OS
- `--ios` flag to include iOS device data in exported reports
- iOS version reporting functionality using Jamf Pro API and [SOFA](https://sofa.macadmins.io) feeds
- Functionality to retrieve mobile device IDs and operating systems from Jamf Classic API
- Bearer Token lifetime checks, Bearer Token expiration written to `.env` file by default

### Changed
- API Role requirements
- Custom exceptions are raised instead during error handling
- `check_token_lifetime` function defaults to `client_id` in `.env`

### Deprecated
- `datetime.utcnow()` deprecated as of Python 3.12 (Gabriel Sroka [@gabrielsroka](https://github.com/gabrielsroka))

### Fixed
- Issue with iOS device export
- Error handling when Token refresh response is `None`
- Issue with Animation continuing after error handling
- Properly await token lifetime checks

### Security
- Patched `urllib3` per [CVE-2024-37891](https://github.com/advisories/GHSA-34jh-p97f-mpxf)
- Patched `requests` per [CVE-2024-35195](https://github.com/advisories/GHSA-9wx4-h78v-vm56)

## [v1.2.1] - 2024-05-11
### Added
- Homebrew Python checks to `installer.sh`
- Traps for `SIGINT` and `SIGTERM`, checks for `.git` configuration on reinstall (#16)

## [v1.2.0] - 2024-04-16
### Added
- Check for `v0` install, attempts to copy `.env` file and fonts directory if found
- `sudo` and `root` checks to install. `-d` or `--develop` arguments passed will download develop branch instead of default

### Changed
- Wrap path in quotes to prevent globbing/word splitting
- Move `uninstall.sh` to tools subdirectory
- `installer.sh` location

### Security
- Patched `idna` per [CVE-2024-3651](https://github.com/advisories/GHSA-jjg7-2v4v-x38h)

## [v1.1.0] - 2024-04-04
### Added
- Release badge
- Bearer Token validation logic and fetching new tokens
- Animation functionality to format error and success messages to `stdout`
- `--user` flag to requirements installation

### Changed
- Date header now includes day by default, additional date formats can be passed with `--date-format` option [#7](https://github.com/liquidz00/Patcher/issues/7)
- Project directory is no longer hidden by default
- Custom fonts are copied into project directory instead of referencing
- Logs are written to log file instead of nested `data` directory

### Removed
- Symlink creation during install

### Security
- Updated pillow per CVE-2024-28219

## [v1.0.0] - 2024-03-28
### Added
- Initial version of Patcher
