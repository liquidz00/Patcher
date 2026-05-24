---
description: "Export Jamf patch reports as Excel, PDF, HTML, or JSON. Covers the CLI, the PatcherClient library, sort and omit flags, and concurrency tuning."
---

(export)=

# Exporting Reports

:::{rst-class} lead
Pulling patch data out of Jamf and into formats you can actually share.
:::

---

By default, a single invocation writes the patch report in all four formats: Excel, PDF, HTML, and JSON. If you only need one or two, narrowing the output is one option away.

## Options

| Flag | Library kwarg | Description |
|---|---|---|
| `--path`, `-p` | `output_dir=` | Where to save the reports (required) |
| `--format`, `-f` | `formats={...}` | Restrict output to specific formats (`excel`, `pdf`, `html`, `json`). Pass multiple times on the CLI |
| `--sort`, `-s` | `sort_by=` | Sort reports by a column |
| `--omit`, `-o` | `omit_recent_hours=48` | Skip patches released in the last 48 hours |
| `--date-format`, `-d` | `date_format=` | PDF header date format (see [Date format](#date-format) below) |
| `--ios`, `-m` | `include_ios=True` | Include iOS device data in reports (see [iOS device data](#ios)) |
| `--concurrency` | `concurrency=` | Max concurrent Jamf API requests. Default: `5` |
| `--device-details`, `-D` | `device_reports=` | Per-title device sheets in the Excel export (slower on large fleets) |
| `--homebrew` / `--no-homebrew` | `enable_homebrew=` / `match_homebrew=` | Also match titles against Homebrew Cask; adds a `Homebrew` coverage column (see [Homebrew matching](#homebrew)) |

## Examples

::::{tab-set}
:sync-group: surface

:::{tab-item} {iconify}`material-icon-theme:console` CLI
:sync: cli

```console
$ patcherctl export --path ~/reports
$ patcherctl export --path ~/reports --format excel
$ patcherctl export --path ~/reports --format html --format pdf
$ patcherctl export --path ~/reports --sort "Released"
$ patcherctl export --path ~/reports --omit
$ patcherctl export --path ~/reports --date-format "Month-Year"
$ patcherctl export --path ~/reports --ios
$ patcherctl export --path ~/reports --concurrency 10
$ patcherctl export --path ~/reports --device-details
$ patcherctl export --path ~/reports --homebrew
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
from pathlib import Path
from patcher import PatcherClient

async with PatcherClient.from_state() as patcher:
    titles = await patcher.fetch_patches(
        sort_by="Released",
        omit_recent_hours=48,
        include_ios=True,
    )
    await patcher.export(
        titles,
        output_dir=Path("~/reports").expanduser(),
        formats={"pdf", "json"},
        date_format="%B %Y",
    )
```

{meth}`fetch_patches <patcher.core.patcher_client.PatcherClient.fetch_patches>` returns a list of {class}`~patcher.core.models.patch.PatchTitle` objects you can inspect or transform before exporting. {meth}`export <patcher.core.patcher_client.PatcherClient.export>` returns the dict of written-file paths, keyed by format.
:::

::::

(date-format)=

### Date format

The PDF header date format defaults to `Month-Day-Year` (e.g. `January 31 2026`). Available options:

| Option | Example |
|---|---|
| `Month-Year` | January 2026 |
| `Month-Day-Year` *(default)* | January 31 2026 |
| `Year-Month-Day` | 2026 April 21 |
| `Day-Month-Year` | 16 April 2026 |
| `Full` | Thursday September 26 2013 |

(concurrency)=

### Concurrency

Patcher fans out Jamf API requests in parallel, capped at 5 concurrent in-flight by default. Increase the cap for faster fetches on instances that can take the load, or lower it for tenants behind aggressive rate limiting.

:::{warning}
Cranking concurrency too high can starve other workloads on your Jamf server. **Stay at or below 5** unless you've coordinated with whoever owns the Jamf instance. See [Jamf's API scalability best practices](https://developer.jamf.com/developer-guide/docs/jamf-pro-api-scalability-best-practices).
:::

## Customizing report appearance

:::{important}
**UI configuration only applies to PDF and HTML formats.** Excel and JSON exports render correctly without any UI configuration. If you're only generating machine-readable reports, you can skip the UI setup entirely.

If you request a PDF export without configuring UI settings first, `patcherctl` will print a warning and continue with placeholder header / footer text. Run `patcherctl reset UI` to configure, or omit `pdf` from `--format`.
:::

PDF report styling (header text, footer text, custom font, logo, HTML header color) is configured via Patcher's property list. See {ref}`property_list_file` for the full plist schema, valid keys, and how to modify them.

A quick summary of what's customizable:

| Key | Affects |
|---|---|
| `header_text` | PDF + HTML report header |
| `footer_text` | PDF footer (page number is appended automatically) |
| `font_name`, `reg_font_path`, `bold_font_path` | PDF font (defaults to [Google's Assistant](https://fonts.google.com/specimen/Assistant)) |
| `logo_path` | PDF logo (PNG/JPEG/Pillow-supported formats) |
| `header_color` | HTML report header color (hex; falls back to `UIDefaults().header_color` when unset) |

`patcherctl reset UI` re-prompts for these settings interactively. See {doc}`reset` for details.

(ios)=

## iOS device data

Passing `--ios` (CLI) or `include_ios=True` (library) appends iOS / mobile device data to the report so you can see what's running on your fleet alongside the macOS patch coverage. Behind the scenes Patcher calls three Jamf APIs:

- {meth}`~patcher.clients.jamf.JamfClient.get_device_ids` pulls the IDs of all enrolled mobile devices.
- {meth}`~patcher.clients.jamf.JamfClient.get_device_os_versions` resolves each ID to its current OS version.
- {meth}`~patcher.clients.jamf.JamfClient.get_sofa_feed` fetches the latest released iOS/iPadOS versions from the [SOFA feed](https://sofa.macadmins.io/) to determine "on the latest" vs "behind."

The aggregate appears in the report as a count of mobile devices on the latest OS. Useful for the same SLA / compliance reporting workflows that drive `--omit` and the `recent-release` analyze criterion.

(homebrew)=

## Homebrew Cask matching

Patcher matches each Jamf patch title against the Installomator-sourced slugs in the Patcher API catalog. Passing `--homebrew` (CLI) or `enable_homebrew=True` (library) widens that to a second dimension: the catalog's [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) source, which covers apps that carry no Installomator label and exposes identity fields (bundle ID, canonical name) that labels often omit.

Matches keep their provenance. An Installomator hit lands in each title's `install_label`; a Homebrew Cask hit lands in the new `homebrew_cask` field; an app covered by both gets both. The Excel, PDF, and HTML reports surface this as a `Homebrew` column listing the matched cask token(s), and the JSON export carries the full structured matches under each title's `homebrew_cask` key.

The flag is off by default, so reports without it stay byte-for-byte unchanged. Homebrew matching rides on the same catalog pass as Installomator, so it has no effect when Installomator matching is turned off.

```python
from pathlib import Path
from patcher import PatcherClient

async with PatcherClient.from_state(enable_homebrew=True) as patcher:
    titles = await patcher.fetch_patches()
    # titles[n].homebrew_cask holds CaskMatch stubs for Cask-covered apps
    await patcher.export(titles, output_dir=Path("~/reports").expanduser())
```
