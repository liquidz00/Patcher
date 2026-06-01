---
description: "Run Patcher unattended via launchd or in CI. Covers non-interactive mode, keyring-backend behavior on non-macOS runners, and a GitHub Actions example."
---

# Automating Patcher

:::{rst-class} lead
Running Patcher on a schedule or in CI/CD pipelines.
:::

---

Create a LaunchAgent on a workstation for time-of-day scheduling, or run Patcher non-interactively with GitHub Actions.

::::{highlights}
{iconify}`octicon:key-16` In-memory credentials
: Passed at runtime and never written to the keychain.

{iconify}`octicon:skip-16` No prompts
: Setup, Installomator, and UI prompts are skipped. Defaults apply instead.

{iconify}`octicon:zap-16` Runs right away
: The command runs as soon as a token is fetched. No wizard, no waiting.
::::

## Scheduling locally

(launch_agent)=

On a workstation, a LaunchAgent runs Patcher on a schedule. It hands scheduling to macOS and writes stdout/stderr to log files you can tail when something misbehaves.

:::{warning}
Make sure both `python3` and `patcherctl` are on your `PATH`. When you install via PyPI, `patcherctl` lands in your Python user-base `bin` directory. See {ref}`add-path` if `patcherctl --version` fails to resolve.
:::

::::{steps}
:::{step} Build the property list file
Customize the example property list below to fit your needs. Specifically, be sure to adjust paths and flags under `ProgramArguments` to match what you'd run by hand. `StartCalendarInterval` configures the schedule the agent will run. Reference [Launched](https://launched.zerowidth.com/) as it is a great helper for building these.

```{code-block} xml
:caption: ~/Library/LaunchAgents/com.liquidzoo.patcher.plist

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.liquidzoo.patcher-export.plist</string>
    <key>ProgramArguments</key>
    <array>
      <string>sh</string>
      <string>-c</string>
      <string>patcherctl export --path /path/to/save --format pdf</string>
    </array>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Application Support/Patcher/logs/patcher-agent.err.log</string>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Application Support/Patcher/logs/patcher-agent.out.log</string>
    <key>StartCalendarInterval</key>
    <array>
      <dict>
        <key>Day</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
      </dict>
    </array>
  </dict>
</plist>
```
:::

:::{step} Deploy and load
```bash
$ cp com.liquidzoo.patcher-export.plist ~/Library/LaunchAgents/
$ chmod 644 ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
$ launchctl load ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
```
:::

:::{step} Verify it's active
```bash
$ launchctl list | grep com.liquidzoo.patcher-export
```
:::
::::

### Test the Configuration

::::{steps}

:::{step} Manually run the export command.

Manually run ``patcherctl export`` command to confirm it executes as expected.
:::

:::{step} Check the logs.

Check the logs for errors or confirmation of success.

Standard Output
: `~/Library/Application Support/Patcher/logs/patcher-agent.out.log`

Standard Error
: `~/Library/Application Support/Patcher/logs/patcher-agent.err.log`
:::

::::

(ci-cd)=

## CI/CD & non-interactive mode

On a CI runner or build server, Patcher runs in **non-interactive mode**. It reads credentials from flags or environment variables, skips every prompt, and keeps no keychain access or saved state.

:::{important}
Credentials can be set via command line flags **or** environment variables. If both are used, command line flags take precedence.
:::

| CLI flag | Environment variable | Description |
|---|---|---|
| `--client-id` | `PATCHER_CLIENT_ID` | Jamf Pro API client ID |
| `--client-secret` | `PATCHER_CLIENT_SECRET` | Jamf Pro API client secret |
| `--url` | `PATCHER_URL` | Jamf Pro instance URL |

### Linux and Keyring

Linux runners do not have a built-in keyring backend by default. To handle this, Patcher automatically detects which platform it is being invoked on, and accordingly installs a null backend automatically. CI runners, containers, and Linux cron jobs just work with no setup. To force a specific backend, set `KEYRING_BACKEND` (Patcher won't override one you've already set).

### Quick example

::::{tab-set}

:::{tab-item} Via flags

```bash
$ patcherctl \
  --client-id="abc-123" \
  --client-secret="my-secret" \
  --url="https://my.jamfcloud.com" \
  export --path=/tmp/reports --format=json
```
:::

:::{tab-item} Via environment

```bash
$ export PATCHER_CLIENT_ID=abc-123
$ export PATCHER_CLIENT_SECRET=my-secret
$ export PATCHER_URL=https://my.jamfcloud.com

$ patcherctl export --path=/tmp/reports --format=json
```
:::

::::

### GitHub Actions workflow

Runs Patcher on a schedule and uploads the JSON report as a build artifact. Adjust schedule, output path, and retention to fit your needs.

```{code-block} yaml
:caption: .github/workflows/patch-report.yml

name: Patch Report

on:
  schedule:
    - cron: '0 13 * * 1-5'  # Weekdays at 13:00 UTC
  workflow_dispatch:

jobs:
  generate-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Patcher
        run: pip install patcherctl

      - name: Generate patch report
        env:
          PATCHER_CLIENT_ID: ${{ secrets.JAMF_CLIENT_ID }}
          PATCHER_CLIENT_SECRET: ${{ secrets.JAMF_CLIENT_SECRET }}
          PATCHER_URL: ${{ secrets.JAMF_URL }}
        run: |
          mkdir -p ./reports
          patcherctl export --path=./reports --format=json

      - uses: actions/upload-artifact@v4
        with:
          name: patch-report
          path: ./reports/*.json
          retention-days: 30
```

JSON pairs well with downstream automation. Feed it into a job that posts to Slack, ingests into a dashboard, or triggers patching policies based on coverage thresholds.

### Library equivalent

The CLI invocation in the workflow above is a convenience over the library API. Drop in a Python script if you'd rather build the report logic in-process. This can be useful when you want to filter or transform titles before exporting, or you're integrating Patcher into an existing automation.

```{code-block} python
:caption: Library callers that pass credentials directly to `PatcherClient(...)` bypass the keyring on every platform.

import asyncio
import os
from pathlib import Path

from patcher import PatcherClient


async def main() -> None:
    async with PatcherClient(
        client_id=os.environ["PATCHER_CLIENT_ID"],
        client_secret=os.environ["PATCHER_CLIENT_SECRET"],
        server=os.environ["PATCHER_URL"],
        disable_cache=True,  # CI runner, no on-disk cache
    ) as patcher:
        titles = await patcher.fetch_patches(sort_by="released")
        await patcher.export(
            titles,
            output_dir=Path("./reports"),
            formats={"json"},
        )


asyncio.run(main())
```

## What's not supported in non-interactive mode

::::{steps}

:::{step} Resetting credentials via `reset`

Designed for keychain workflows. In CI, update the secrets and re-run.
:::

:::{step} Interactive setup (`--fresh`)

Non-interactive mode skips the setup state machine entirely, so this flag does nothing.
:::

:::{step} Customization prompts

PDF header, footer, and logo use built-in defaults. To customize the PDF, configure UI settings on a workstation first and commit the plist values to your CI image, or generate JSON and style it downstream.
:::
::::
