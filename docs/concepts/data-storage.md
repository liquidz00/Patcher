(property_list_file)=

# Local data storage

:::{rst-class} lead
Where Patcher writes on your Mac, and how to inspect, modify, or reset every piece of it.
:::

Patcher writes to three locations on your Mac. Knowing what lives where makes it easier to inspect, reset, or relocate state when something goes wrong.

| Location | Contents |
|---|---|
| `~/Library/Application Support/Patcher/` | Property list (configuration), cached Installomator labels, unmatched-apps file, custom fonts and logo |
| `~/Library/Caches/Patcher/` | Cached patch report data |
| Login keychain (service `Patcher`) | Jamf API URL, Client ID, Client Secret, OAuth token + expiration |

## Application Support directory

Everything Patcher writes outside of the keychain and the patch-data cache lives under `~/Library/Application Support/Patcher/`:

```
~/Library/Application Support/Patcher/
├── com.liquidzoo.patcher.plist       # Configuration (this page)
├── .labels/                          # Cached Installomator label scripts
├── unmatched_apps.json               # Jamf titles with no Installomator label match
├── fonts/                            # Custom PDF report fonts (if any)
├── logo.png                          # Custom PDF report logo (if any)
└── logs/                             # LaunchAgent stdout/stderr (if scheduled)
```

To wipe this directory entirely, use `patcherctl reset full`. To wipe just the patch-data cache (separate location, see below), use `patcherctl reset cache`.

## Property list file

The property list at `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist` stores persistent configuration: UI customization for PDF/HTML reports, setup state, and integration toggles.

(v2_format_change)=

### Format

```{versionchanged} 2.1.1
The property list format was updated for clarity and consistency. Patcher migrates the old format automatically on first run and writes a backup before doing so.
```

| Setting | Old key | New key |
|---|---|---|
| UI settings dict | `UI` | `UserInterfaceSettings` |
| Header text | `HEADER_TEXT` | `header_text` |
| Footer text | `FOOTER_TEXT` | `footer_text` |
| Font name | `FONT_NAME` | `font_name` |
| Regular font path | `FONT_REGULAR_PATH` | `reg_font_path` |
| Bold font path | `FONT_BOLD_PATH` | `bold_font_path` |
| Logo path | `LOGO_PATH` | `logo_path` |
| HTML header color | *N/A* | `header_color` |
| Setup completion | `first_run_done` (nested) | `setup_completed` (top-level) |
| Installomator toggle | *N/A* | `enable_installomator` |

(modify_plist)=

### Modifying the plist

Use `PlistBuddy` or a code editor. The `defaults` command works but struggles with nested dictionaries; `PlistBuddy` is more reliable for keys inside `UserInterfaceSettings`.

:::{dropdown} Editing binary plists in a text editor
:icon: code

`.plist` files default to binary format, which most text editors can't read. Convert to XML first:

```console
$ plutil -convert xml1 ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

After editing, convert back to binary:

```console
$ plutil -convert binary1 ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```
:::

### UI customization keys

`UserInterfaceSettings` is the dict that holds branding for PDF and HTML reports: `header_text`, `footer_text`, `font_name`, `reg_font_path`, `bold_font_path`, `logo_path`, and `header_color`. For per-key descriptions, defaults, and the three ways to set them (CLI wizard, `PlistBuddy`, or `ui_config=` on `PatcherClient`), see {doc}`/getting-started/customization`.

(installomator_support)=

### Installomator toggle

The `enable_installomator` boolean controls whether Patcher matches Jamf titles against Installomator labels:

```console
$ defaults write ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist enable_installomator -bool false
```

See {ref}`disabling_installomator_support` for the full behavior breakdown.

### Setup completion

```console
$ /usr/libexec/PlistBuddy -c "Print :setup_completed" ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
true
```

:::{warning}
Don't edit `setup_completed` by hand. To re-run setup, use `patcherctl --fresh` or `patcherctl reset full`. See {doc}`/getting-started/setup/cli` for details.
:::

(full_example_config)=

### Full example

```xml
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
</dict>
</plist>
```

## Patch data cache

Patch report data fetched from Jamf is cached at `~/Library/Caches/Patcher/`. This is what powers `patcherctl analyze` against "the latest report" without re-fetching, and what `--all-time` trend analysis reads across.

To wipe the cache: `patcherctl reset cache` (CLI) or `patcher.data.reset_cache()` (library). To skip caching entirely on a per-invocation basis, construct {class}`~patcher.PatcherClient` with `disable_cache=True`.

## Credentials in keychain

Jamf credentials live in the macOS login keychain under the service name `Patcher`:

| Account | Value |
|---|---|
| `URL` | Jamf Pro instance URL |
| `CLIENT_ID` | Jamf API client ID |
| `CLIENT_SECRET` | Jamf API client secret |
| `TOKEN` | Current OAuth access token (managed by Patcher) |
| `TOKEN_EXPIRATION` | Token expiration timestamp (managed by Patcher) |

The CLI's setup wizard writes the first three; the {class}`~patcher.client.token_manager.TokenManager` manages the last two automatically. Library callers pass credentials in-memory to {class}`~patcher.PatcherClient` and bypass the keychain entirely (see {doc}`/getting-started/setup/library`).

To inspect the entries: open **Keychain Access**, switch to the **login** keychain, and filter by `Patcher`. To clear them: `patcherctl reset creds` (all) or `patcherctl reset creds --credential url` (one at a time).
