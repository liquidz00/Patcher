---
description: "Where Patcher writes on your Mac: the Application Support directory, patch-data cache, and login keychain. How to inspect, modify, or reset each."
---

(data_storage)=

# Data Storage

:::{rst-class} lead
Where Patcher writes on your Mac, and how to inspect, modify, or reset each piece.
:::

---

(application_support_dir)=

## Application Support Directory

Everything Patcher writes outside of the keychain and the patch-data cache lives under `~/Library/Application Support/Patcher/`:

```text
~/Library/Application Support/Patcher/
├── com.liquidzoo.patcher.plist       # Configuration (this page)
├── unmatched_apps.json               # Titles with no label match
├── fonts/                            # Custom PDF report fonts (if any)
├── logo.png                          # Custom PDF report logo (if any)
└── logs/                             # LaunchAgent stdout/stderr (if scheduled)
```

Older versions also kept a `.labels/` directory of cached label scripts. That cache is gone; Patcher removes any leftover directory automatically on the next run and on `reset cache`.

To wipe this directory entirely, use `patcherctl reset full`. To wipe just the patch-data cache (separate location, see below), use `patcherctl reset cache`.

(property_list_file)=

### Property List File

The property list at `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist` stores persistent configuration such as UI customization for PDF/HTML reports, setup state, and integration toggles.

(v2_format_change)=

:::{card} {iconify}`material-icon-theme:xml` Property list keys

`UserInterfaceSettings`
: UI settings dict

`header_text`
: Header text

`footer_text`
: Footer text

`font_name`
: Font name

`reg_font_path`
: Regular font path

`bold_font_path`
: Bold font path

`logo_path`
: Logo path

`header_color`
: HTML header color

`setup_completed`
: Setup completion

`enable_matching`
: Master matching toggle (renamed from `enable_installomator` in v3.3.0)

`enable_caching`
: Patch-data cache toggle

`integrations`
: Per-source matching dict (`installomator`, `homebrew`, `autopkg`, `jai`)

`ignored_titles`
: Jamf-title patterns (`fnmatch` syntax) to skip during matching

`interpreter_path`
: Python interpreter path initially used to store credentials in Keychain
:::

(modify_plist)=

:::{seealso}

For customization commands, see {doc}`customizing reports </getting-started/customization>`.
:::

(installomator_support)=

#### Matching Toggle

The `enable_matching` boolean is the master switch for catalog matching: when false, Patcher skips all source matching on every invocation and the `install_label` field on every {class}`~patcher.core.models.patch.PatchTitle` stays empty. The `integrations` dict toggles individual sources (`installomator`, `homebrew`) when matching is on. See {ref}`disabling_installomator_support` for the full behavior breakdown and the command to flip it.

#### Full Example

(full_example_config)=

```{code-block} xml
:caption: {iconify}`material-icon-theme:xml` Full plist example

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>UserInterfaceSettings</key>
    <dict>
        <key>header_text</key>
        <string>AnyOrg Patch Report</string>
        <key>footer_text</key>
        <string>Made with &lt;3 from IT</string>
        <key>font_name</key>
        <string>Assistant</string>
        <key>reg_font_path</key>
        <string>/Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Regular.ttf</string>
        <key>bold_font_path</key>
        <string>/Users/jappleseed/Library/Application Support/Patcher/fonts/Assistant-Bold.ttf</string>
        <key>header_color</key>
        <string>#6432bdff</string>
        <key>logo_path</key>
        <string>/Users/jappleseed/Library/Application Support/Patcher/logo.png</string>
    </dict>
    <key>setup_completed</key>
    <true/>
    <key>enable_matching</key>
    <true/>
    <key>enable_caching</key>
    <true/>
    <key>integrations</key>
    <dict>
        <key>installomator</key>
        <true/>
        <key>homebrew</key>
        <false/>
        <key>autopkg</key>
        <false/>
        <key>jai</key>
        <false/>
    </dict>
    <key>ignored_titles</key>
    <array/>
    <key>interpreter_path</key>
    <string>/usr/local/bin/managed_python3</string>
</dict>
</plist>
```

(patch_data_cache)=

## Patch Data Cache

Patch report data fetched from Jamf is cached at `~/Library/Caches/Patcher/`. This lets Patcher's analysis reuse the latest report without re-fetching it, and it's what trend analysis reads across when comparing multiple snapshots over time.

Snapshots are stored as Parquet (`patch_data_<timestamp>.parquet`), a format that survives pandas upgrades. Caches written by older versions (`.pkl`) are still read where the installed pandas can load them; if a legacy snapshot can't be read, run `patcherctl reset cache` to clear it and re-export.

:::{note}

To skip caching entirely on a per-invocation basis, construct {class}`~patcher.core.patcher_client.PatcherClient` with `disable_cache=True`.
:::

(keychain_creds)=

## Credentials in Keychain

Jamf credentials live in the macOS login keychain under the service name `Patcher`:

| Account | Value |
|---|---|
| `URL` | Jamf Pro instance URL |
| `CLIENT_ID` | Jamf API client ID |
| `CLIENT_SECRET` | Jamf API client secret |
| `TOKEN` | Current OAuth access token (managed by Patcher) |
| `TOKEN_EXPIRATION` | Token expiration timestamp (managed by Patcher) |

The CLI's setup wizard writes the first three and the {class}`~patcher.clients.token_manager.TokenManager` manages the last two automatically.

:::{admonition} Security
:class: danger

Patcher stores these values on disk in plaintext. Both the client secret and bearer token are wrapped in `pydantic.SecretStr` so accidental `repr`, `model_dump`, or traceback rendering shows the masked placeholder rather than the secret. Library code reaching the raw value calls `.get_secret_value()` explicitly (see `PatcherClient.fetch_patches` and the OAuth refresh path in `TokenManager.fetch_token`).
:::
