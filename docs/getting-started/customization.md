---
description: "Customize Patcher's PDF and HTML report branding. Header, footer, font, logo, and HTML accent color via the CLI wizard, plist, or PatcherClient."
---

(customization)=

# Customization

:::{rst-class} lead
Tailor Patcher's PDF and HTML reports to match your organization's branding.
:::

Customizable branding covers the header and footer text, the PDF font, an optional company logo, and the HTML report's header color. The sample below shows where each element ends up.

```{image} ../_static/example_pdf.png
:alt: Example PDF
:width: 750px
:align: center
```

:::{important}
UI customization affects **PDF and HTML reports only**. Excel and JSON exports never read these settings. See [Customizing report appearance](/guides/export.md#customizing-report-appearance) in the export docs for the full story.
:::

## How customization works

Three flows. Pick whichever fits your environment:

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:console` CLI wizard
:sync: wizard

The simplest path. `patcherctl reset UI` walks you through every UI setting in order and writes the result to your property list. Run it once when onboarding, or any time you want to refresh your branding.

```console
$ patcherctl reset UI
```

The wizard prompts for header text, footer text, font choice, optional logo, and HTML header color.

:::

:::{tab-item} {iconify}`material-icon-theme:xml` Manual plist edit
:sync: plist

Best for scripted provisioning where you want to seed Patcher's branding before any user runs the wizard. Use `PlistBuddy` to write directly to the property list:

```console
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:header_text 'AnyOrg Patch Report'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

Per-key examples are in the sections below. For the full plist schema (including non-UI keys), see {ref}`property_list_file`.

:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

Pass a `ui_config` dict when constructing {class}`~patcher.core.patcher_client.PatcherClient`. Values stay in memory for the lifetime of the client; nothing is written to disk.

```python
from patcher import PatcherClient

async with PatcherClient(
    client_id="...",
    client_secret="...",
    server="https://yourorg.jamfcloud.com",
    ui_config={
        "header_text": "AnyOrg Patch Report",
        "footer_text": "Made with <3 from IT",
        "font_name": "Helvetica",
        "reg_font_path": "/path/to/Helvetica-Regular.ttf",
        "bold_font_path": "/path/to/Helvetica-Bold.ttf",
        "logo_path": "/path/to/logo.png",
        "header_color": "#6432bdff",
    },
) as patcher:
    titles = await patcher.fetch_patches()
    await patcher.export(titles, output_dir="~/reports", formats={"pdf"})
```

This is the natural fit for CI/CD pipelines, ephemeral runners, or services that need per-tenant branding.

:::

::::

The rest of the page covers each element in detail, with both a `PlistBuddy` command and a library snippet. Pick whichever flow fits, or mix them.

## Customizable Elements

### Editing the Header & Footer Text

`header_text` sits at the top of every report. `footer_text` sits at the bottom of every PDF page (the page number is appended automatically with ` | <n>`). Both are plain strings, no length cap.

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:xml` plist
:sync: plist

```console
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:header_text 'AnyOrg Patch Report'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:footer_text 'Made with <3 from IT'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
ui_config = {
    "header_text": "AnyOrg Patch Report",
    "footer_text": "Made with <3 from IT",
}
```

:::

::::

### Customizing the Font

The PDF font is controlled by three keys: a display name, a path to the regular weight `.ttf`, and a path to the bold weight `.ttf`. The default is [Google's Assistant](https://fonts.google.com/specimen/Assistant), bundled with Patcher.

:::{warning}
Custom fonts can introduce alignment or spacing quirks in the PDF. Run a test export after switching to verify everything still lines up the way you expect.
:::

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:xml` plist
:sync: plist

```console
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:font_name 'Helvetica'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:reg_font_path '/path/to/Helvetica-Regular.ttf'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:bold_font_path '/path/to/Helvetica-Bold.ttf'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
ui_config = {
    "font_name": "Helvetica",
    "reg_font_path": "/path/to/Helvetica-Regular.ttf",
    "bold_font_path": "/path/to/Helvetica-Bold.ttf",
}
```

:::

::::

### Customizing the HTML Report Header Color

`header_color` is the accent color used on the HTML report's header banner. It accepts a hex string with or without the `#` prefix, and optionally an alpha channel (`#RRGGBBAA`). The default is `#6432bdff` (Patcher purple).

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:xml` plist
:sync: plist

```console
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:header_color '#0071bc'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
ui_config = {
    "header_color": "#0071bc",
}
```

:::

::::

## Company Logo

A logo on the PDF report ties branding together. Patcher places the logo in the report header alongside `header_text`.

### Supported Logo Requirements

- **File formats**: PNG, JPEG, or any [Pillow-supported image format](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#fully-supported-formats).
- **Validation**: Patcher loads the file via Pillow before accepting it; corrupt or unreadable images are rejected at runtime.
- **Path requirements**: Use an absolute path. The wizard copies the file to `~/Library/Application Support/Patcher/logo.png` and stores that path in the plist, so you only need the file to exist long enough for the copy.

:::{tip}
Need to generate a logo file from an existing icon? SAP's [`macOS-icon-generator`](https://github.com/SAP/macOS-icon-generator) produces standardized PNG icons at the right resolutions. To copy an absolute path from Finder: hold ⌥, right-click the file, and select **Copy "filename" as Pathname**.
:::

### Configuring a Logo

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:console` CLI wizard
:sync: wizard

`patcherctl reset UI` prompts for a logo path during the UI walkthrough. If you provide one, Patcher copies the file to its Application Support directory and writes the resulting path to the plist.

:::

:::{tab-item} {iconify}`material-icon-theme:xml` plist
:sync: plist

```console
$ /usr/libexec/PlistBuddy -c "Set :UserInterfaceSettings:logo_path '/path/to/logo.png'" \
  ~/Library/Application\ Support/Patcher/com.liquidzoo.patcher.plist
```

If you set the path manually, copy the logo file somewhere stable yourself. Patcher won't move it.

:::

:::{tab-item} {iconify}`material-icon-theme:python` Library
:sync: library

```python
ui_config = {
    "logo_path": "/path/to/logo.png",
}
```

The path is consulted at export time. Make sure the file is readable by whatever process runs Patcher.

:::

::::

## Persistence

When you customize via the CLI (wizard or `PlistBuddy`), values are written to Patcher's property list at `~/Library/Application Support/Patcher/com.liquidzoo.patcher.plist` and persist across runs. When you customize via the library (`ui_config=`), values stay in memory for the lifetime of the `PatcherClient` and disappear when the process exits.

For the full plist schema, the v2 format-change history, and details on every other key Patcher stores there, see {ref}`property_list_file`.
