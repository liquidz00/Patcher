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
├── .labels/                          # Cached label scripts
├── unmatched_apps.json               # Titles with no label match
├── fonts/                            # Custom PDF report fonts (if any)
├── logo.png                          # Custom PDF report logo (if any)
└── logs/                             # LaunchAgent stdout/stderr (if scheduled)
```

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

`enable_installomator`
: Installomator toggle

`interpreter_path`
: Python interpreter path initially used to store credentials in Keychain
:::

(modify_plist)=

:::{seealso}

For customization commands, see {doc}`customizing reports </getting-started/customization>`.
:::

(installomator_support)=

#### Installomator Toggle

The `enable_installomator` boolean controls whether Patcher matches Jamf titles against Installomator labels. When false, the package skips Installomator-sourced matching entirely on every invocation. See {ref}`disabling_installomator_support` for the full behavior breakdown and the command to flip it.

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
    <key>enable_installomator</key>
    <true/>
    <key>interpreter_path</key>
    <string>/usr/local/bin/managed_python3</string>
</dict>
</plist>
```

(patch_data_cache)=

## Patch Data Cache

Patch report data fetched from Jamf is cached at `~/Library/Caches/Patcher/`. This lets Patcher's analysis reuse the latest report without re-fetching it, and it's what trend analysis reads across when comparing multiple snapshots over time.

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
