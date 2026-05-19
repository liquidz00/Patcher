---
description: "Every patcherctl flag, subcommand, exit code, and environment variable in one place. Hand-maintained reference; the Makefile is the source of truth."
---

(cli-reference)=

# CLI Reference

:::{rst-class} lead
Every `patcherctl` command, every flag, every environment variable, every exit code. The single source of truth when you need to look up a switch.
:::

```{important}
The Click decorators in `src/patcher/cli/__init__.py` are the runtime source of truth. This page is maintained by hand because `sphinx-click` doesn't introspect `asyncclick` cleanly. If you find drift between this page and `patcherctl --help`, the `--help` output wins; open an issue or PR to bring this page back in sync.
```

## Synopsis

```text
patcherctl [<global-options>] <command> [<command-options>]
```

Running `patcherctl` with no arguments enters the interactive setup wizard on first launch, or prints `--help` on subsequent runs. See {doc}`/getting-started/setup` for the setup flow.

## Global options

These apply to every subcommand and are passed before the subcommand name.

| Flag | Type | Default | Description |
|---|---|---|---|
| `--version` | flag | — | Print Patcher's version and exit |
| `--help` | flag | — | Print the help message and exit |
| `--debug`, `-x` | flag | off | Enable debug (verbose) logging |
| `--disable-cache` | flag | off | Skip the on-disk patch-data cache for this invocation |
| `--fresh` | flag | off | Re-run setup from scratch, ignoring saved completion state |
| `--client-id <id>` | string | — | Jamf API client ID; engages non-interactive mode when paired with `--client-secret` and `--url` |
| `--client-secret <secret>` | string | — | Jamf API client secret |
| `--url <url>` | string | — | Jamf Pro instance URL (e.g. `https://yourorg.jamfcloud.com`) |

## Environment variables

| Variable | Description |
|---|---|
| `PATCHER_CLIENT_ID` | Same as `--client-id`. Set together with the other two to engage non-interactive mode |
| `PATCHER_CLIENT_SECRET` | Same as `--client-secret` |
| `PATCHER_URL` | Same as `--url` |
| `KEYRING_BACKEND` | Optional override. On non-macOS platforms Patcher auto-installs `keyring.backends.null.Keyring`; set this only if you want a specific custom backend. See {ref}`linux-keyring`. |

Flags take precedence over env vars when both are set.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error (raised `PatcherError` or user-facing issue) |
| `2` | Unhandled exception (an unexpected bug; please report) |
| `3` | Setup error (wizard could not complete) |
| `4` | API error (Jamf returned an unexpected response, auth failure, etc.) |
| `130` | Interrupted by Ctrl+C |

## {iconify}`lucide:file-output` `patcherctl export`

Pull patch data from Jamf and write it to disk in one or more formats.

```text
patcherctl export --path <dir> [options]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--path <dir>`, `-p` | path | required | Directory to write report file(s) into |
| `--format <fmt>`, `-f` | choice | all four | One of `excel`, `html`, `pdf`, `json`. Pass multiple times to emit multiple formats |
| `--sort <column>`, `-s` | string | — | Sort patch reports by a column name (e.g. `released`, `completion_percent`) |
| `--omit`, `-o` | flag | off | Drop titles with patches released in the last 48 hours |
| `--date-format <fmt>`, `-d` | choice | `Month-Day-Year` | PDF header date format. Choices: `Month-Year`, `Month-Day-Year`, `Year-Month-Day`, `Day-Month-Year`, `Full` |
| `--ios`, `-m` | flag | off | Include enrolled mobile device version counts in reports |
| `--concurrency <n>` | int | `5` | Maximum concurrent Jamf API requests. Don't exceed [Jamf's recommended ceiling](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices) unless you've coordinated with the instance owner |
| `--device-details`, `-D` | flag | off | Include per-title device-detail sheets in the Excel export (Excel only) |

**Examples**

```console
$ patcherctl export --path ~/reports --format pdf --format json
$ patcherctl export -p ~/reports -f pdf --sort released --omit
$ patcherctl export -p ~/reports --ios --device-details
```

See {doc}`/usage/export` for the full export walkthrough.

## {iconify}`lucide:bar-chart-3` `patcherctl analyze`

Filter or trend patch data. Reads the latest cached patch dataset (or an explicit Excel file) and outputs a table to stdout, optionally writing an HTML summary.

```text
patcherctl analyze --criteria <name> [options]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--criteria <name>`, `-c` | string | required | Filter or trend criterion. See tables below for accepted values |
| `--excel-file <path>`, `-e` | path | — | Use a specific Excel report instead of the latest cached dataset |
| `--all-time`, `-a` | flag | off | Analyze trends across every cached dataset instead of a single snapshot |
| `--threshold <pct>`, `-t` | float | `70.0` | Completion-percent threshold for the `below-threshold` filter |
| `--top-n <n>`, `-n` | int | — | Limit results to the top N entries |
| `--summary`, `-s` | flag | off | Write an HTML summary report alongside the stdout table |
| `--output-dir <dir>`, `-o` | path | — | Directory for the HTML summary (required if `--summary` is passed) |

**Filter criteria** (use without `--all-time`)

| Value | Returns |
|---|---|
| `most-installed` | Titles ordered by absolute hosts-patched count, descending |
| `least-installed` | Same, ascending |
| `oldest-least-complete` | Oldest patches with the lowest completion percent |
| `below-threshold` | Titles with completion below `--threshold` |
| `high-missing` | Titles where missing patches exceed 50% of total hosts |
| `recent-release` | Patches released in the last week |
| `zero-completion` | Titles at 0% completion |
| `top-performers` | Titles above 90% completion |
| `installomator` | Titles that match an Installomator label (automation-ready) |

**Trend criteria** (use with `--all-time`)

| Value | Returns |
|---|---|
| `patch-adoption` | Adoption curve over time across cached snapshots |
| `release-frequency` | How often new patches land per title |
| `completion-trends` | Completion-percent trajectory per title |

**Examples**

```console
$ patcherctl analyze -c most-installed --top-n 10
$ patcherctl analyze -c below-threshold --threshold 50
$ patcherctl analyze -c patch-adoption --all-time --summary --output-dir ~/reports
```

See {doc}`/usage/analyze` for the full analyze walkthrough.

## {iconify}`lucide:rotate-ccw` `patcherctl reset`

Reset Patcher state. Run the wizard again, drop credentials, wipe the cache, or do all of it at once.

```text
patcherctl reset <kind> [options]
```

**Kinds** (case-insensitive, positional argument)

| Kind | Effect |
|---|---|
| `full` | Wipe credentials, UI configuration, cached patch data, and setup state. Re-launches the setup wizard at the end. |
| `UI` | Reset PDF/HTML branding (header, footer, font, logo, header color) and prompt for new values |
| `creds` | Re-prompt for Jamf credentials. With `--credential`, prompt for just one of them |
| `cache` | Empty `~/Library/Caches/Patcher/`. No-op when `--disable-cache` is in effect |

**Options**

| Flag | Type | Default | Description |
|---|---|---|---|
| `--credential <kind>`, `-c` | choice | all three | When `kind=creds`, reset only the named credential. Choices: `url`, `client_id`, `client_secret` |

**Examples**

```console
$ patcherctl reset cache
$ patcherctl reset creds --credential url
$ patcherctl reset UI
$ patcherctl reset full
```

See {doc}`/usage/reset` for the full reset walkthrough.
