<!-- markdownlint-capture -->
<!-- markdownlint-disable -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **API documentation built out** at `docs/api/endpoints.md` and `docs/api/examples.md`. Endpoints page covers auth, base URL, caching semantics (ETag + Cache-Control + If-None-Match), every `/apps*` endpoint with parameters and response shapes, error reference, and OpenAPI schema pointer. Examples page has tab-set blocks with `bash` (curl) and `python` (httpx) for setup, list/filter/fetch/sources/generate-label, ETag-aware revalidation, full pagination loops, and error handling. Roadmap note for a future `PatcherAPIClient` helper class. The deploy-internal `/admin/catalog/upload` endpoint is intentionally omitted from the public docs.
- **README mention of the Patcher API**. Short section pointing readers to <https://api.patcherctl.dev> and the docs, with the private-beta + Slack-access framing matching `docs/api/endpoints.md`. README scope otherwise unchanged (still primarily a `patcherctl` library + CLI README).
- **Catalog-hash ETag and Cache-Control headers** on `/apps*` responses. The catalog DB's SHA-256 (computed once on API startup) becomes the `ETag` value for every read response; `Cache-Control: public, max-age=300, stale-while-revalidate=3600` authorizes Cloudflare and well-behaved clients to cache. Revalidating clients sending `If-None-Match` get a 304 short-circuit that skips the route function entirely (no DB read). Because the hash changes exactly when the catalog deploys (and never otherwise), this combination typically takes 90%+ of read traffic off the origin between refreshes. Scoped to GETs against `/apps*`; admin endpoints, `/health`, and POSTs bypass.
- **GitHub Actions catalog-refresh workflow** at `.github/workflows/refresh-catalog.yml`. Runs daily at 04:00 UTC and on-demand via `workflow_dispatch`. Walks all five ingest scripts (Installomator with resolver enabled, Homebrew Cask, MAS, AutoPkg, JAI), runs stitch, uploads the resulting DB to `https://api.patcherctl.dev/admin/catalog/upload` with a per-run-generated SHA-256 integrity header. Single required secret: `PATCHER_DEPLOY_TOKEN`. Concurrency-guarded so overlapping schedules and manual triggers queue rather than stomp each other. The DB is also saved as a 7-day workflow artifact for diagnostic recovery. Replaces the manual local-ingest + scp + ssh-swap dance entirely.
- **Push-based catalog deployment via `POST /admin/catalog/upload`.** New admin route, deploy-token auth, file-watch swap automation, and GitHub-issue alerting form a complete push-deploy pipeline that replaces the manual scp + ssh dance for catalog refreshes. Components:
  - `DeployToken` model (separate `deploy_tokens` table; SHA-256 hashed at rest like user tokens). User tokens cannot authorize admin endpoints and vice versa; revoking one class doesn't affect the other.
  - `get_current_deploy_token` FastAPI dependency mirroring `get_current_user` but scoped to the deploy table.
  - `POST /admin/catalog/upload` endpoint: streams the request body to `{incoming_dir}/patcher_api.db.tmp`, verifies an optional `X-Catalog-SHA256` integrity header against the computed body hash, atomically renames to the watched filename, enforces a configurable max-upload size (default 100 MB, reject 413). Cleans up the `.tmp` on any failure path so future uploads aren't confused by stale partials.
  - `api/scripts/grant_deploy_token.py` mirrors `grant_token.py` but writes to the deploy table.
  - `api/deploy/swap-patcher-catalog.sh` is the systemd-invoked swap script: stops `patcher-api.service`, backs up the live DB with a timestamped filename to `/var/lib/patcher-api/backups/`, moves the staged file into place, restores ownership + mode, restarts the API, prunes backups older than `PATCHER_BACKUP_RETENTION_DAYS` (default 14). On any failure, attempts a best-effort rollback from the just-made backup before alerting.
  - `api/deploy/patcher-catalog-swap.path` + `.service` are the systemd unit pair that watches `/var/lib/patcher-api/incoming/patcher_api.db` and triggers the swap script on `PathChanged`.
  - **GitHub-issue alerting on failure.** The swap script opens an issue in `liquidz00/Patcher` with the failing command, last 30 lines of `journalctl -u patcher-api`, a `df -h` snapshot, the script's own transcript, and the path to the most recent backup. The MacAdmins Slack `#patcher` channel subscribes to the repo, so an issue triggers a Slack notification automatically (no Slack app permissions required from the user's account). Configurable via `PATCHER_ALERT_GITHUB_TOKEN`, `PATCHER_ALERT_GITHUB_REPO`, and `PATCHER_ALERT_ON_SUCCESS` (off by default; cleaner signal-to-noise for failure-only routing).
  - `api/deploy/README.md` is the one-time Linode setup checklist: directories, install commands, GitHub PAT scope, env file additions, deploy-token mint, end-to-end verification, failure recovery, and disabling instructions.

### Fixed
- **MAS slug collisions in stitch phase 3 now merge instead of skip.** Previously, a MAS app whose slugified `trackName` collided with an existing apps row (typically a phase-2 Cask-only entry like `microsoft-word` or `xcode`) was logged + dropped, silently losing the MAS payload for popular apps (Microsoft Office, Apple Pro Suite). The new `_attach_mas_to_existing_app` helper merges the payload into the existing row: appends `"mas"` to `sources` in canonical order via a new `_canonicalize_sources` helper, and writes the mas `source_detail` payload without touching the row's name/vendor/version/download_url. New `mas_merged_apps` counter in the `stitch_catalog` return tuple tracks merge hits separately from `mas_only_apps` (new MAS-only rows).
- **AutoPkg ingest log noise quieted.** The upstream `autopkg/index` payload has ~1000 malformed records (shared-processor recipes with `name: null`, app recipes with missing `shortname` due to special characters in the upstream index's shortname construction). Previously each one produced a multi-line Pydantic ValidationError warning, burying every other log line. Now the schema accepts null `name` and `shortname` (since stitch matching already gates on a non-empty normalized name, these recipes naturally never attach to apps anyway), and the residual skip cases are aggregated into a single summary warning per reason with up to 3 example identifiers each. Empirically takes the ingest log from ~1000 multi-line warnings to a handful of one-liners.

### Changed
- **`GET /apps` filters and pagination now push fully into SQL** via SQLite's JSON1 extension. Previously, `source` and `exclude_source` filters were applied in Python *after* materializing every row that matched the SQL-level `vendor` predicate, which silently made `limit` describe the post-fetch Python slice rather than the actual filtered page. The new query uses `EXISTS (SELECT 1 FROM json_each(apps.sources) WHERE value = :source)` to push membership checks into SQLite, and `LIMIT`/`OFFSET` apply against the filtered result so pagination is meaningful. JSON1 is built into the sqlite3 module Python ships against; no new dependency.
- **SQLite connection PRAGMAs** wired via a SQLAlchemy `connect` event hook in `patcher_api.db`: `journal_mode=WAL`, `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` (64 MB per connection), `mmap_size=268435456` (256 MB memory-mapped reads). WAL is the load-bearing one: concurrent reads no longer block each other or block writes. The cache + mmap settings keep hot pages in memory after first access, so typical requests don't touch disk after warmup.
- **`patcher.core.installomator.resolve()` now returns a `ResolveOutcome` discriminated union** instead of the prior `ResolveResult` dataclass. Three variants: `Resolved(value)` for usable values, `Unresolvable(reason)` for pipelines that never produced output (unsupported command, parse error, network failure, empty output), and `InvalidOutput(raw, reason)` for values that came back but failed sanity checks (failed URL validation, etc). Callers pattern-match on the variant instead of checking sentinel string values like `method == "literal"`. `ResolveResult` is removed.
- **URL validation moved inside `resolve()` itself.** Pass `is_url=True` to opt into the check; `looks_like_clean_http_url` runs against the final value and failures land as `InvalidOutput(raw=value, reason=...)`. Removes the bolt-on validation pattern in `api/patcher_api/ingest/installomator.py::_resolve_or_null` (the `is_url` kwarg there is still accepted and threaded through, but the actual check lives in `resolve()`).

### Added
- **Native pyinstallomator command coverage expanded** with minimal-viable implementations of the highest-frequency commands real Installomator labels use: `awk` (only `-F sep '{print $N}'`), `sed` (only `s/X/Y/[g]` and `-E 's/X/Y/[g]'`), `tr` (translate + `-d` delete), `sort` (plain + `-r` + `-n`), `uniq` (trivial dedup of adjacent lines). Anything outside those subsets still raises `UnsupportedOperation`. Tracks the parked plan to do native expansion before subprocess fallback.
- **Subprocess fallback for unsupported pipelines**, opt-in via `resolve(..., allow_subprocess_fallback=True)`. When native dispatch raises `UnsupportedOperation`, the pipeline string is passed to `/bin/bash -c` with a stripped env (PATH-only), 30-second timeout, and `shell=False`. Off by default. Trade-off: the pipeline string itself is still interpreted by bash, which is a real (accepted) shell-injection surface area for callers that pin the Installomator commit hash and trust the pipeline-string corpus. Callers can layer this behind their own env-var gate.
- **Jamf App Installers (JAI) catalog source.** New `jamf_app_installers` table, ingest module (`patcher_api.ingest.jamf_app_installers`), Pydantic schemas, and `api/scripts/ingest_jamf_app_installers.py`. Source is the public HTML catalog page on `learn.jamf.com` (`~345` titles in a single ~110KB fetch). The catalog renders as a three-column table (Title Name, Source, Host Name); a small regex anchored on the `headers="reference-7022__entry__N"` attribute extracts each row. Upstream's `"--"` placeholder for the Jamf-hosted case is normalized to `None` at the ingest boundary. **Coverage-indicator only** today: the public HTML lacks bundle_id, version, download URL, and the Jamf Software Title ID. When live Jamf Pro access becomes available, the unlisted endpoint that exposes those richer fields can extend the model in place.
- **JAI matching in stitch.** Catalog rows attach to existing apps via the same normalized-name matching (`_normalize_name`) used for AutoPkg, applied across all three stitch phases. JAI never creates new app rows. `stitch_catalog` return tuple expanded to seven elements with `jai_attached_apps` as the new counter.
- **Canonical source ordering pinned across all sources:** `[installomator, homebrew_cask, autopkg, jamf_app_installer, mas]`. Apps land with sources in this order regardless of which subset matched.
- **AutoPkg recipe-index catalog source.** New `autopkg_recipes` table, ingest module (`patcher_api.ingest.autopkg`), Pydantic schemas, and `api/scripts/ingest_autopkg.py` script. Source is the canonical recipe index at `github.com/autopkg/index/blob/main/index.json` (rebuilt every ~4h by upstream; ~15,000 recipes in a single ~10MB JSON fetch). Patcher catalogs recipes as a **coverage indicator only**, never executing them, because AutoPkg recipe execution is macOS-bound and the catalog is meant to be source-agnostic. Each app row gains an `autopkg` source-detail payload listing the matched recipes (identifier, name, shortname, repo, path, parent_identifier, inferred_type, and a constructed `recipe_url`). Multiple recipes per app is the common case (Firefox alone typically has 5–10 child variants across maintainer repos); all matches are preserved.
- **AutoPkg name matching in stitch.** Recipes attach to existing apps via a normalized-name match (`_normalize_name` strips whitespace and non-alphanumerics + lowercases, so `"Google Chrome"` and `"GoogleChrome"` both match `"googlechrome"`). Attachment happens across all three stitch phases: Installomator-led, Cask-only, and MAS-only. AutoPkg never creates new app rows; its presence is purely a coverage signal. `stitch_catalog` return tuple expanded to include an `autopkg_attached_apps` counter (count of apps with one or more recipes attached across all phases).
- **`AutopkgSource` Pydantic schema rewritten** to support multiple recipes per app: `AutopkgSource(recipes: list[AutopkgRecipeEntry])` replaces the prior single-recipe `AutopkgSource(recipe_name, recipe_url)` shape. No production callers of the old shape existed at the time of the change; the seed data and tests have always used `autopkg=None`.
- **Mac App Store (MAS) catalog source.** New `mas_apps` table, ingest module (`patcher_api.ingest.mas`), Pydantic schemas, and a curated seed list of ~20 well-known MAS bundle IDs covering Apple's iWork suite, developer / pro media tools, and popular third-party paid apps (Pixelmator Pro, Things, Fantastical, TablePlus, Microsoft Office). Apple's iTunes Lookup API is the upstream (the only place the legacy "iTunes" name appears; everywhere else in the codebase uses **mas** since iTunes is retired branding). New `api/scripts/ingest_mas.py` runs the sweep; rate-limited at one request every three seconds to stay under Apple's ~20 req/min ceiling. Full sweep takes ~1 minute for the default seed.
- **MAS source in stitch.** `stitch_catalog` gained a phase 3 that joins MAS records to existing `apps` rows by `bundle_id` (an Installomator label whose `packageID` matches a MAS record now gets `"mas"` added to its `sources` list and a `mas` source-detail payload attached) and creates new app rows for MAS-only apps (Apple's first-party iWork, Pro apps, etc., that aren't covered by Installomator or Homebrew Cask). Source ordering on the apps table is now canonical: `[installomator, homebrew_cask, autopkg, mas]` regardless of which subset is present. New `MasSource` Pydantic schema, new `mas` JSON column on `app_source_details`, MAS-only-slug-collision defense in phase 3 (skips and logs rather than silently overwriting an existing apps row via `ON CONFLICT DO UPDATE`).
- **`GET /apps` now accepts `limit` and `offset` query parameters** for pagination. `limit` defaults to 100 and accepts 1–1000; `offset` defaults to 0. Results are ordered by `slug` so pagination is deterministic across requests. Prior to this commit the route silently ignored any `limit` parameter and returned every row in the catalog (~8000), forcing FastAPI's response-model validation to walk the entire result set on every request and surfacing any single bad row (e.g. an `ftp://` URL) as a 500 across all callers. Existing filter parameters (`vendor`, `source`, `exclude_source`) apply before pagination, so `limit` describes the page size of the filtered result rather than the raw table.
- **`patcher.core.installomator.looks_like_clean_http_url`** as a public helper. Sanity-checks that a value is a single, reasonably-sized http(s) URL safe to store in columns later serialized as Pydantic `HttpUrl`. Catches HTML response bodies (vendor returned non-2xx but `curl` didn't error), multi-line concatenations (the pipeline's final filter was unsupported so the full `grep` output landed in the value), `ftp://` schemes, and oversized URLs (2000-char ceiling, 83 chars of headroom under `HttpUrl`'s 2083 limit). Used by the Patcher API ingest and stitch layers; library callers stitching their own catalogs can apply the same gate.
- **`PatcherClient` is now usable as an async context manager**, with a new `aclose()` method that releases the underlying httpx connection pool. Library callers can wrap construction in `async with PatcherClient(...) as patcher:` for guaranteed cleanup on block exit (preferred); `aclose()` is also callable directly and is idempotent.
- `Installomator.list_available_labels()`, `get_label(name)`, and reshaped `get_labels(names=None)` as public methods. Suitable as library entry points for callers that want to enumerate or fetch labels without going through the full matching flow.
- Comprehensive test coverage for the Installomator matching pipeline (`tests/test_installomator.py`, 26 tests) covering Labels.txt discovery, single-label fetch, batch fetch, team-ID filtering, fuzzy matching thresholds, and the full `match()` pipeline including the second-pass + unmatched-apps persistence path.
- Integration test scaffolding under `tests/integration/`. Opt-in via `make test-integration`; default `make test` continues to run unit tests only. Defaults to Jamf's published dummy instance (`dummy.jamfcloud.com`) with credential overrides via `PATCHER_INTEGRATION_URL`, `PATCHER_INTEGRATION_CLIENT_ID`, `PATCHER_INTEGRATION_CLIENT_SECRET`. Documented in the contributing guide.
- `httpx>=0.28.1` dependency in preparation for the upcoming transport migration away from `/usr/bin/curl` subprocess calls.
- `BaseAPIClient.http` (lazy `httpx.AsyncClient`), `BaseAPIClient.aclose()`, and `BaseAPIClient.fetch_text()` — the first httpx-backed surface, sitting alongside the existing curl-based methods. `fetch_text` translates httpx exceptions to `APIResponseError` (with `not_found=True` on 404) so callers see the same exception contract as `fetch_json`. No existing call sites changed in this commit; subsequent commits migrate callers one at a time.
- **TLS trust uses the OS's native trust store via `truststore`.** Adds `truststore` as a runtime dependency and configures `BaseAPIClient.http` with a `truststore.SSLContext`. Corporate CAs installed at the OS level (macOS Keychain, Windows Certificate Store, Linux's `/etc/ssl/certs/`) — typically pushed via MDM in enterprise environments running TLS-inspecting proxies (Zscaler, Netskope, Cloudflare Gateway, etc.) — are now trusted automatically with no per-application configuration. Replaces the legacy "edit certifi's cacert.pem" workaround.
- `params=` keyword on `BaseAPIClient.fetch_text()` for forwarding query parameters to httpx. Accepts both a mapping and a list of `(key, value)` tuples so callers with repeated keys (e.g., Jamf's CSV export endpoint's `columns-to-export`) work without manual `urlencode`.
- GitHub issue templates migrated to YAML forms: `bug_report.yml`, `feature_request.yml`, `feedback.yml`, plus `config.yml` controlling the picker behavior and contact links.
- `.cursor/rules/` domain rules for Jamf Pro API, Installomator, Jamf App Installers, AutoPkg, and Homebrew — referenced by AI coding assistants for accurate, schema-grounded suggestions when editing related code.
- `.claude/skills/check-app-match/` — a Claude skill that enumerates which patching methods (Installomator, Homebrew Cask, AutoPkg) cover a given Mac application, surfacing matches per ecosystem with confidence flags.
- Read the Docs versioned documentation: the `develop` branch builds independently with a navbar version switcher between `latest` (stable, from `main`) and `develop` (unreleased). Develop builds also surface a banner indicating users are reading unreleased docs.

### Changed
- **`InstallomatorClient` no longer requires Jamf credentials for label-only operations.** `InstallomatorClient()` defaults its `api` to a fresh `HTTPClient` (which has no keyring/credentials touchpoint) instead of constructing a `JamfClient` internally. Library callers can use `InstallomatorClient().list_available_labels()` / `get_label()` standalone without any Jamf auth. `match()` still requires Jamf (it calls `get_app_names`); pass `api=<JamfClient>` at construction — `PatcherClient` does this automatically for its `installomator` attribute. Calling `match()` on a Jamf-less instance raises a clear `PatcherError` pointing at the fix instead of an opaque `AttributeError`.
- **Installomator matching pipeline rewritten** to use the upstream `Labels.txt` file at the repository root for fast discovery, fetching individual `.sh` fragments lazily and only for matched titles. First-run HTTP calls drop from ~700 to ~(1 + matched_count) — first-run matching time drops from minutes to seconds. Public `Installomator.match()` API unchanged; on-disk cache layout at `~/Library/Application Support/Patcher/.labels/` preserved.
- **Installomator's HTTP transport migrated from curl to httpx.** `list_available_labels()` and `get_label()` now call `BaseAPIClient.fetch_text()` instead of shelling out to `/usr/bin/curl`. No subprocess fork per request, fewer string-parsing trapdoors, and connection pooling between fragment fetches. The exception contract is preserved: a 404 still surfaces as `APIResponseError(not_found=True)` and is silently absorbed in `get_label()`'s best-effort path; other API errors still propagate as `PatcherError` for `Labels.txt` fetch failures.
- **`fetch_json()` migrated from curl to httpx.** Public signature unchanged; the curl-string-parse-status-code trick (`-w "\nSTATUS:%{http_code}"` followed by `rsplit("\nSTATUS:")` to recover the body) is gone. Status codes come from `response.status_code` directly. Form-encoded vs JSON request bodies are still routed by `Content-Type` header. Network errors translate to `APIResponseError("Network error fetching URL")`; non-2xx still flows through `_handle_status_code` with the `not_found=True` flag on 404. Validated end-to-end against `dummy.jamfcloud.com` via the integration test suite — the full basic→bearer OAuth flow succeeds on the new transport.
- **`fetch_basic_token()` migrated from curl to httpx.** HTTP Basic Authentication now uses httpx's native `auth=(username, password)` tuple parameter, which encodes credentials in the `Authorization` header — the password never appears in URL, request body, or log output, so the prior `_sanitize_command()` step is no longer needed for this code path. The `create_roles` and `create_client` setup methods were already migrated transitively via the `fetch_json` rewrite. After this commit, no auth-flow code in `BaseAPIClient` shells out to curl; only the unused `execute()` / `execute_sync()` methods remain on the legacy path (cleanup landing in Commit 5).
- **`ApiClient.get_title_report_csv()` migrated from curl to httpx.** Replaces the `curl + -w "\nSTATUS:%{http_code}"` body-and-status-in-one-shot trick with a direct `fetch_text(url, headers=..., params=...)` call. Status codes now come from httpx's response object directly; the body is parsed via `csv.DictReader` unchanged. The list-of-tuples `query_params` form (one entry per `columns-to-export` column) is forwarded to httpx, which handles URL encoding.
- **`ApiClient.get_sofa_feed()` migrated from curl to httpx.** Now delegates to `fetch_json` rather than shelling out for the JSON feed at `sofafeed.macadmins.io`. The earlier docstring rationale about subprocess SSL handling is obsolete — `truststore`-backed verification covers the same scenarios with no per-call workaround.
- **`UIConfigManager._download_fonts()` migrated from `BaseAPIClient.execute_sync` (curl subprocess) to a synchronous `httpx.get` call**, configured with a `truststore.SSLContext` for parity with the async transport so the same enterprise-CA story applies to default-font downloads. Font binary content writes to disk via `Path.write_bytes()`. `UIConfigManager` no longer holds a `BaseAPIClient` instance.
- Project version bumped to `2.5.0.dev0` on the `develop` branch to surface the in-development state. Stable releases continue from `main`.

### Changed (infrastructure)
- **Documentation moved to `docs.patcherctl.dev`** (custom domain) from `patcher.readthedocs.io`. Read the Docs continues to host the build; only the public URL changed. The old URL still resolves via RTD's canonical redirect, so external links don't rot. README, package metadata, CLI help strings, GitHub release notes template, issue-picker contact links, and Sphinx `html_baseurl` config all updated to the new domain. Historical CHANGELOG entries referencing the old URL are intentionally left intact as a record of where the docs lived at the time of those releases.
- **API moved to `https://api.patcherctl.dev`** (named Cloudflare Tunnel) from the per-restart random `*.trycloudflare.com` quick-tunnel URL. Same Linode origin, same systemd-managed cloudflared process; the tunnel now uses a stable token-bound configuration so the public URL persists across restarts. cloudflared still terminates TLS at the Cloudflare edge with no inbound ports opened on Linode.

### Changed (documentation restructure)
- **Sphinx docs reorganized around audience-neutral topics.** The previous `docs/user/` + `docs/library/` split mirrored the codebase rather than the reader's task and broke down once Patcher became library AND CLI. New top-level sections: `getting-started/`, `usage/`, `integrations/`, `concepts/`, `api/` (private beta service), `reference/` (auto-generated), `support/` (FAQ + troubleshooting). Sidebar uses captioned root toctrees with `globaltoc_expand_depth: 1` so section parents (e.g. Setup) auto-expand their children. Old `docs/user/...html` and `docs/library/...html` URLs no longer resolve; `README.md` and `CHANGELOG.md` link targets updated accordingly.
- **Theme migrated from pydata-sphinx-theme to Shibuya.** Per-mode brand accents (grape in light, dodger blue in dark) track the v2 logo. Tab-sets for parallel CLI/library examples, `{iconify}` role for inline icons, `lead` blocks on every page, PDF UI defaults now print a warning when `--format pdf` is requested without UI customization.
- **Customization split out of the property-list reference.** `concepts/data-storage` is now a reference for what Patcher writes where (Application Support, Caches, login keychain) with brief pointers to per-key docs. `getting-started/customization` is the authoritative how-to for header/footer text, fonts, logo, and HTML header color, showing CLI wizard, `PlistBuddy`, and `PatcherClient(ui_config=...)` flows side-by-side.
- **New auto-generated reference pages** for `PatcherClient`, `report`, `terminal_logger`, `fonts`, `models/fragment`, `models/label`, `models/ui` — public surfaces previously missing from `docs/reference/`.

### Fixed
- **Patcher API ingest and stitch now validate resolved URL outputs before storing them in `download_url` columns.** Previously, when `PATCHER_API_RESOLVE_INGEST=true` engaged the pyinstallomator resolver, pipelines that succeeded at the shell level but produced garbage (HTML error pages, newline-joined lists of URLs from unsupported final filters, `ftp://` schemes) had their output stored verbatim. Pydantic's `HttpUrl` type rejected those values at response-serialization time, surfacing as `ResponseValidationError` 500s on the `/apps` endpoint. The `_resolve_or_null` helper now applies `looks_like_clean_http_url` on both the resolution-on and resolution-off paths for URL fields; `stitch._resolve_download_url` and `stitch._clean_cask_url` apply the same gate before propagating either a label URL or a Cask URL to the apps table. The Cask URL gate is shared between phase 1 (label-with-Cask fallback) and phase 2 (Cask-only apps) so a Cask with an `ftp://` URL can't slip past the validator by lacking an Installomator label match.

### Removed (documentation restructure)
- `docs/user/` and `docs/library/` directories. All content migrated into the new topic-based layout above.
- `docs/ext/styled_params.py` Sphinx extension. Shibuya's default `:param:` field-list rendering covers the same visual need without a custom extension.

### Changed (decouple click from core)
- **Logger split.** `core/logger.py` is now stdlib-only — `LogMe` simply delegates to a `logging.Logger`, and `PatcherLog.custom_excepthook` logs unhandled exceptions to file without touching the terminal. A new `cli/terminal_logger.py` holds a `TerminalHandler` (logging handler that emits click-styled lines) and `install_terminal_excepthook()` (chains a CLI-styled stderr message onto the core hook). The CLI installs both inside the `cli()` callback so library imports inherit none of these side effects.
- **UI prompts moved from `core/ui_manager.py` to `cli/setup.py`.** `setup_ui`, `configure_font`, and `configure_logo` are now `Setup.prompt_ui_settings`, `Setup.prompt_font_config`, `Setup.prompt_logo_config`. `core/ui_manager.py` no longer imports `asyncclick` or `Pillow`; the UI config object is pure persistence + font download for library callers.
- **`ReportManager.process_reports` and `_success` moved to a new `cli/report.py`.** `process_reports` is now a free function taking a `ReportManager` instance; the click-styled success banner lives next to it. The remaining `ReportManager` methods (`_validate_directory`, `_sort`, `_omit`, `_ios`, `calculate_ios_on_latest`) stay in `core/` as reusable building blocks. `core/report_manager.py` no longer imports `asyncclick`.
- **`Animation` moved back to `cli/`** (where it originally belonged per the layer plan) now that `core/report_manager.py` no longer needs it. The circular import that forced it to `core/` in Phase 1a is gone with `process_reports` out.
- **Module-level `sys.excepthook` and `warnings` mutations in `cli/__init__.py` moved into `cli()`.** They no longer fire on `import patcher.cli` — only on actual CLI invocation. Library callers that touch `patcher.cli.setup` for any reason no longer get a process-wide excepthook swap as a side effect.

### Removed
- **`ReportManager` class and `core/report_manager.py`.** Once `PatcherClient` became the facade holding `jamf`, `data`, and `installomator`, `ReportManager` was a redundant helper-bag wrapping the same references. Its remaining methods moved to module-level functions in :mod:`patcher.core.analyze`:
  - `_sort` → :func:`sort_titles`
  - `_omit` → :func:`omit_recent`
  - `_ios` → :func:`append_ios_status` (now takes the ``JamfClient`` as an explicit parameter)
  - `calculate_ios_on_latest` (underscore dropped; public)
  `_validate_directory` was inlined into ``cli/report.py::_validate_output_dir`` (its only caller).
- :attr:`PatcherClient.report` attribute — removed. Library callers use the analyze functions directly.

### Added (Phase 6 — PatcherClient facade + cli/library separation)
- **`PatcherClient`** at `patcher.PatcherClient` — the headline library entry point. Wraps `JamfClient`, `DataManager`, `InstallomatorClient`, and `ReportManager` as attributes, plus carries the UI config dict. Constructible two ways: direct credentials (`PatcherClient(client_id=..., client_secret=..., server=...)`) for library use, or with an existing `ConfigManager` (`PatcherClient(config=existing_config)`) for the CLI's keyring-backed path.
- **`patcher.core.fonts.ensure_default_fonts(target_dir)`** — standalone helper that downloads the Assistant Regular and Bold fonts via httpx with truststore. Library callers generating PDF reports can ensure the default fonts are available without instantiating `UIConfigManager`. Idempotent.
- **`InstallomatorClient.__init__` accepts `api=` parameter** for dependency injection. When a configured `JamfClient` is supplied, `InstallomatorClient` uses it for the Jamf API calls inside `match()` (specifically `get_app_names`); otherwise it constructs its own. `PatcherClient` passes its shared `JamfClient` automatically so library callers don't need to wire it themselves.

### Changed
- **`PropertylistManager` moved from `core/` to `cli/`.** Its only role was CLI-session persistence (setup_completed, UI config); library callers with in-memory state don't need plist. Old import path (`patcher.core.plist_manager`) is gone — use `patcher.cli.plist_manager` if the CLI surface is needed externally.
- **`UIConfigManager` moved from `core/` to `cli/`.** Plist-coupled config + interactive setup is CLI-only. The httpx-based font download was extracted to `patcher.core.fonts.ensure_default_fonts` so library callers still have access to that utility.
- **`PDFReport` decoupled from `UIConfigManager`.** Now accepts a plain `ui_config: dict` (defaults to `UIDefaults().model_dump()`), no longer constructs a `UIConfigManager` internally. Added graceful font fallback: when the configured font paths don't exist on disk, falls back to fpdf's built-in Helvetica instead of failing. Library callers can now generate PDFs without the CLI's plist-backed UI config.
- **`process_reports` (in `cli/report.py`) now takes a `PatcherClient`** instead of a `ReportManager`. Attribute access updated: `patcher.jamf` (was `report_manager.api_client`), `patcher.data` (was `report_manager.data_manager`), `patcher.installomator` (was `report_manager.iom`), `patcher.report` (the bag of helpers like `_validate_directory`, `_sort`, `_omit`, `_ios`).
- **Test fixtures updated** (`tests/conftest.py`): `patcher_instance` returns a mock-shaped `PatcherClient` instead of a `ReportManager`. The new shape uses a real `ReportManager` as `patcher.report` for helper access. `mock_ui_config_manager` renamed to `mock_ui_config_dict` (returns the dict shape PDFReport now expects).
- **Public facade slimmer** in `patcher/__init__.py`. Headline: `PatcherClient`. Still public: `JamfClient`, `InstallomatorClient`, `PatchTitle`, `PatchDevice`, exceptions. Hidden via submodule path: `HTTPClient`, `ConfigManager`, `DataManager`, `JamfCredentials`, `AccessToken`, `Label`, `SetupError`.

### Fixed
- **Phase 5 rename collateral**: the bulk sed substitution `Installomator → InstallomatorClient` had butchered URL constants and prose in `core/installomator.py` — the upstream Installomator project's GitHub URL became `InstallomatorClient/InstallomatorClient` (broken in production, since `Labels.txt` would have 404'd). URLs restored; class name remains `InstallomatorClient`.

### Changed (Phase 5 — class renames for clarity)
- **`BaseAPIClient` → `HTTPClient`** (lives in `patcher.client`). The class is generic httpx-with-truststore plumbing — the new name reflects what it is, not what it isn't.
- **`ApiClient` → `JamfClient`** (file renamed `client/api_client.py` → `client/jamf.py`). The class is Jamf-specific; the rename makes that explicit and sets up the per-service-client naming pattern (future `HomebrewClient`, `AutoPkgClient`, etc.).
- **Pydantic `JamfClient` model → `JamfCredentials`** (file renamed `core/models/jamf_client.py` → `core/models/jamf.py`). Frees the `JamfClient` name for the API client. The model carries client_id + client_secret + server URL — `JamfCredentials` is the honest name.
- **`Installomator` → `InstallomatorClient`** (stays in `core/installomator.py`). Sets the per-service-client naming pattern alongside `JamfClient`. User-facing docs and prose continue to refer to the upstream "Installomator" project; only the class name is suffixed with `Client`.
- **`patcher.client.token_manager.attach_client()`** return type is now `JamfCredentials` (was `JamfClient` — the same model class under the old name).
- **Variable cleanup**: `self.jamf_client` → `self.jamf_credentials` on the `JamfClient` (formerly `ApiClient`); the `mock_jamf_client` test fixture → `mock_jamf_credentials`.
- **Public facade trimmed** in `patcher/__init__.py`. Exposed: `JamfClient`, `InstallomatorClient`, `PatchTitle`, `PatchDevice`, and the exceptions (`PatcherError`, `APIResponseError`, `CredentialError`, `TokenError`, `InstallomatorWarning`). Hidden (still importable via submodule path): `HTTPClient`, `ConfigManager`, `DataManager`, `JamfCredentials`, `AccessToken`, `Label`, `SetupError`. The CLI-only `Setup`, `SetupType`, `UIConfigManager`, `Animation`, `PropertylistManager` are not re-exported. Setup is documented as the CLI-only flow; library callers go through `JamfClient.from_credentials`.

### Added (Phase 4 — library ergonomics)
- **`ApiClient.from_credentials(client_id, client_secret, server, concurrency=5)`** classmethod factory. Library callers can construct an `ApiClient` directly from credentials without setting up a `ConfigManager` themselves; the factory wires the credentials into an in-memory `ConfigManager` (the same path the CLI uses for `--client-id`/`--client-secret`/`--url`). No keyring backend required, no plist mutation, no disk I/O on construction.
- **Public package facade** at `src/patcher/__init__.py`. The common library entry points — `ApiClient`, `BaseAPIClient`, `ConfigManager`, `DataManager`, `Installomator`, the Pydantic models (`PatchTitle`, `PatchDevice`, `JamfClient`, `AccessToken`, `Label`), and exceptions (`PatcherError`, `APIResponseError`, `CredentialError`, `SetupError`, `TokenError`, `InstallomatorWarning`) — are now importable directly from `patcher`. Submodule paths under `patcher.cli`, `patcher.core`, and `patcher.client` remain importable but are no longer the recommended public surface. The CLI-only `Setup` class is deliberately not re-exported.

### Changed (Phase 3c — cleanup audit)
- **Narrowed broad `except Exception:` blocks** to the realistic failure modes for each call site. `_read_plist_file` / `_write_plist_file` now catch `(plistlib.InvalidFileException, OSError)`; the plist deletion and cache-reset `unlink()` paths catch `OSError`; `UIConfigManager.reset_config` catches `PatcherError` (the only thing `plist_manager.remove` raises); `get_title_report_csv`'s CSV row-parse loop catches `(pydantic.ValidationError, TypeError)`. The two genuinely-needed broad catches — the CLI's top-level `sys.excepthook` delegation and `Animation.error_handling`'s context-manager catch+reraise pattern — are kept.
- **`BaseAPIClient._handle_status_code` renamed and refactored to `_raise_for_status`.** The old version returned the response body on 2xx and raised on non-2xx — a return-or-raise smell that made callers like `fetch_json` read as `return self._handle_status_code(...)` while actually meaning "this may raise." The new shape mirrors httpx's `response.raise_for_status()`: a void method that raises on non-2xx and returns nothing; the caller returns `response_json` directly. The exception contract (status code, `not_found=True` on 404, error message extraction) is unchanged.
- **`BaseAPIClient.concurrency` property replaced with `set_concurrency(int)` method.** The previous `@property` + `@concurrency.setter` pair wrapped `self.max_concurrency` with a getter that did nothing and a setter that validated. Reads now go through the `max_concurrency` attribute directly; validated writes use `set_concurrency()`. One less Python-ceremony pattern wrapping a plain attribute.
- **`PatcherError` docstring strengthened** with a `.. important::` admonition flagging the kwarg-to-attribute injection as load-bearing for the 404 short-circuit in `Installomator.match()`. The mechanism is the same; the docstring now makes the "do not cleanup" signal explicit to readers.
- Removed empty `Model.__init__(self, **kwargs): super().__init__(**kwargs)` no-op from `core/models/__init__.py` — Pydantic's `BaseModel.__init__` already does this.
- Removed stale `# noinspection PyUnresolvedReferences` annotation on `cls.model_fields.keys()` in `core/models/label.py` — Pydantic v2 documents `model_fields` as a public class attribute.

### Removed
- **`Setup.SetupStage` state machine and `SetupStateManager` class** (`cli/setup.py`). The 5-stage progress machine (NOT_STARTED → API_CREATED → HAS_TOKEN → JAMFCLIENT_SAVED → COMPLETED), the JSON state file at `~/Library/Application Support/Patcher/.setup_stage.json`, the four per-stage methods (`not_started`, `api_created`, `has_token`, `jamfclient_saved`), the `stage`/`_stage`/`stage_map` attributes, and the dispatch loop in `Setup.start()` are all gone. The original motivation — letting users resume an interactive setup that failed after the API role/client was created on the Jamf side — no longer earns its complexity now that Patcher serves both library and CLI use cases. `Setup.start()` is now a straightforward linear flow; the single `setup_completed` plist boolean remains as the "has setup finished?" tracker. The `--fresh` flag still works and now means *"re-run setup even when already completed"* instead of *"ignore saved stage and restart"*. Partial-failure recovery — if a Standard setup fails after the role/client is created — is now a documented manual operation (delete the objects in Jamf, or switch to SSO setup).
- **`check_token` decorator** (`client/decorators.py`). The decorator called `TokenManager.ensure_valid_token()` and converted `ValidationError → TokenError` — but every `ApiClient` method already calls `self._headers()`, which itself calls `ensure_valid_token()`. Token validation was running twice per request. The `ValidationError → TokenError` conversion moved into `ensure_valid_token()` directly. All seven `@check_token` decorations and the module are gone.
- `BaseAPIClient.execute()`, `BaseAPIClient.execute_sync()`, `BaseAPIClient._sanitize_command()`, and `BaseAPIClient._format_headers()` — the legacy curl-subprocess transport. All HTTP in Patcher now flows through httpx via the lazy `BaseAPIClient.http` property (async) or one-shot `httpx.get` (sync, for font downloads). The credential-redaction step that scrubbed curl arglists before logging is no longer needed because httpx never serializes credentials into argv. `subprocess` and `asyncio.create_subprocess_exec` are no longer imported anywhere in the codebase.
- `ShellCommandError` exception class. Removed from `utils/exceptions.py` after the last raiser was removed.

### Changed (directory restructure)
- **Source split into `client/`, `core/`, and `cli/` layers under `src/patcher/`.** The transport layer (`BaseAPIClient`, `ApiClient`, `TokenManager`, `decorators`) stays in `client/`. Domain logic and managers (`exceptions`, `logger`, `plist_manager`, `config_manager`, `ui_manager`, `data_manager`, `pdf_report`, `report_manager`, `analyze`, `installomator`, `animation`, `models/`) move to `core/`. CLI surface (`cli/__init__.py`, `cli/setup.py`) moves to `cli/`. The `api/` directory at the repo root is reserved for the future Patcher API service and is **not** packaged into the Python distribution.
- All internal and test imports have been updated to the canonical new paths. Re-export shims from Phase 1 have been removed; the `utils/` and `models/` legacy directories no longer exist. Sphinx autodoc and cross-reference paths in `docs/` updated to match. **Breaking for any external code importing from `patcher.utils.*` or `patcher.models.*`** — update imports to `patcher.core.*` / `patcher.core.models.*`. `patcher.client.decorators` replaces `patcher.utils.decorators`. `patcher.cli.setup` replaces `patcher.client.setup`.

### Fixed
- `PatcherError` instances now expose their constructor kwargs as instance attributes (e.g. `err.not_found`, `err.status_code`). Restores the intended 404 short-circuit in `Installomator.match()`, which previously always fell through to the generic re-raise because `getattr(e, "not_found", False)` evaluated against `self.context["not_found"]` (a dict entry) instead of an attribute, returning `False` even on 404 responses.
- Sphinx documentation builds no longer fail under Read the Docs' `-W` flag: the custom `styled_params` extension now declares its parallel-read/write safety, matching the pattern already used by the `ghwiki` extension.
- Integration test fixture (`iom`) now patches `ApiClient` before `Installomator` construction, so the Linux CI runners (which lack a keyring backend) no longer fail with `NoKeyringError` when constructing the test target.

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
