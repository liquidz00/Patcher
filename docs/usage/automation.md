---
description: "Run Patcher unattended via launchd or in CI. Covers non-interactive mode, the KEYRING_BACKEND requirement for Linux runners, and a GitHub Actions example."
---

# Automation

:::{rst-class} lead
Run Patcher unattended, either locally on a schedule with `launchd` or in CI/CD pipelines.
:::

Two patterns cover most automation needs: a `launchd` LaunchAgent on a workstation for time-of-day scheduling, or non-interactive invocations on ephemeral runners (GitHub Actions, Linux build agents, anything without a keychain).

## Scheduling locally with `launchd`

(launch_agent)=

For a workstation that runs Patcher on a schedule, a `launchd` LaunchAgent is the cleanest option. It hands the scheduling off to macOS and writes stdout/stderr to log files you can tail when something misbehaves.

:::{dropdown} What's a LaunchAgent?
:animate: fade-in-slide-down
:icon: bookmark

A LaunchAgent is a macOS service configuration file used to run tasks on behalf of logged-in users. It's part of the `launchd` system and is ideal for scheduling recurring user-scoped actions like report exports.
:::

:::{warning}
Make sure both `python3` and `patcherctl` are on your `PATH`. When you install via PyPI, `patcherctl` lands in your Python user-base `bin` directory. See {ref}`add-path` if `patcherctl --version` fails to resolve.
:::

### 1. Build the `.plist` file

Customize the example below. The two key fields:

- **`ProgramArguments`**: the `patcherctl export` invocation. Adjust paths and flags to match what you'd run by hand.
- **`StartCalendarInterval`**: the schedule. [Launched](https://launched.zerowidth.com/) is a great helper for building these.

```{code-block} xml
:caption: Run on the 1st of each month at 09:00

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

### 2. Deploy and load

```bash
cp com.liquidzoo.patcher-export.plist ~/Library/LaunchAgents/
chmod 644 ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
launchctl load ~/Library/LaunchAgents/com.liquidzoo.patcher-export.plist
```

Verify it's active:

```bash
launchctl list | grep com.liquidzoo.patcher-export
```

### 3. Testing the Configuration

To ensure the LaunchAgent is working:

1. Manually run the ``patcherctl export`` command to confirm it executes as expected.
2. Check the logs for errors or confirmation of success:
   - **Standard Output**: ``~/Library/Application Support/Patcher/logs/patcher-agent.out.log``
   - **Standard Error**: ``~/Library/Application Support/Patcher/logs/patcher-agent.err.log``

(ci-cd)=

## CI/CD & non-interactive mode

For ephemeral environments (GitHub Actions runners, Linux build agents, etc.), Patcher runs in **non-interactive mode** — also called `in_memory_credentials` mode internally; the same mode {class}`PatcherClient <patcher.PatcherClient>` engages when library callers pass `client_id`, `client_secret`, and `server` directly. No keychain access, no setup wizard, no persistent state.

### Engaging non-interactive mode

Provide all three credentials via CLI flags **or** environment variables (mix-and-match is fine; flags take precedence):

| CLI flag | Environment variable | Description |
|---|---|---|
| `--client-id` | `PATCHER_CLIENT_ID` | Jamf Pro API client ID |
| `--client-secret` | `PATCHER_CLIENT_SECRET` | Jamf Pro API client secret |
| `--url` | `PATCHER_URL` | Jamf Pro instance URL |

In non-interactive mode, Patcher:

::::{tab-set}

:::{tab-item} {iconify}`lucide:key-round` Memory-only credentials
:sync: creds

Credentials are held in memory for the lifetime of the invocation. The macOS keychain is never read or written. Right for ephemeral runners and Docker containers where there's no persistent secret store anyway.
:::

:::{tab-item} {iconify}`lucide:skip-forward` Skips every interactive prompt
:sync: prompts

Setup type, Installomator support, and UI configuration are all bypassed. Any code path that would normally pause for input proceeds with sane defaults instead.
:::

:::{tab-item} {iconify}`lucide:eraser` No completion persistence
:sync: no-persist

Setup completion is not written to disk. The next invocation must provide credentials again, which is exactly what you want on ephemeral runners that wipe their filesystem between jobs.
:::

:::{tab-item} {iconify}`lucide:zap` Runs immediately
:sync: immediate

The requested subcommand executes as soon as an access token is fetched. No wizard, no prompts, no waiting.
:::

::::

(linux-keyring)=

### {iconify}`simple-icons:linux` Linux runners: keyring backend

`patcherctl` imports the [`keyring`](https://pypi.org/project/keyring/) library as part of its credential plumbing. On Linux, `keyring` requires a backend that talks to a session keyring (typically Secret Service via D-Bus); CI runners and headless servers don't have one, which historically meant the import would crash before Patcher had a chance to run.

Patcher now handles this automatically. On any non-macOS platform, importing `patcher` installs the no-op `keyring.backends.null.Keyring` so that CI runners, Docker containers, scheduled cron jobs on Linux servers, and Windows hosts all just work — no env-var dance required. Non-interactive mode never reads or writes the keychain anyway, so the null backend has no behavioral cost.

```{important}
If you want a specific custom backend (e.g. a real Secret Service backend on a graphical Linux desktop), set `KEYRING_BACKEND` explicitly. Patcher honors an existing `KEYRING_BACKEND` env var and does not overwrite it.
```

### Quick example

::::{tab-set}

:::{tab-item} Via flags

```bash
patcherctl \
  --client-id="abc-123" \
  --client-secret="my-secret" \
  --url="https://my.jamfcloud.com" \
  export --path=/tmp/reports --format=json
```
:::

:::{tab-item} Via environment

```bash
export PATCHER_CLIENT_ID=abc-123
export PATCHER_CLIENT_SECRET=my-secret
export PATCHER_URL=https://my.jamfcloud.com

patcherctl export --path=/tmp/reports --format=json
```
:::

::::

### GitHub Actions workflow

Runs Patcher on a schedule and uploads the JSON report as a build artifact. Adjust schedule, output path, and retention to suit.

```yaml
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

The CLI invocation in the workflow above is a convenience over the library API. Drop in a Python script if you'd rather build the report logic in-process — useful when you want to filter / transform titles before exporting, or you're integrating Patcher into an existing automation runtime:

```python
import asyncio
import os
from pathlib import Path

from patcher import PatcherClient


async def main() -> None:
    async with PatcherClient(
        client_id=os.environ["PATCHER_CLIENT_ID"],
        client_secret=os.environ["PATCHER_CLIENT_SECRET"],
        server=os.environ["PATCHER_URL"],
        disable_cache=True,  # ephemeral runner; no on-disk cache wanted
    ) as patcher:
        titles = await patcher.fetch_patches(sort_by="released")
        await patcher.export(
            titles,
            output_dir=Path("./reports"),
            formats={"json"},
        )


asyncio.run(main())
```

Same `KEYRING_BACKEND` requirement applies — set it before invoking `python`. Library callers benefit from one additional advantage: arbitrary transforms between `fetch_patches()` and `export()` (filter to a subset, decorate titles, push to multiple destinations) without piping through the CLI's output formats.

### Security considerations

- **Never commit credentials to your repository.** Use GitHub Secrets (or your CI platform's equivalent).
- **Use a dedicated API client** for CI/CD. Minimum privileges, easy to rotate independently of your interactive account. See {doc}`../getting-started/jamf-api`.
- **Rotate the client secret periodically.** Treat it like any other long-lived credential.

### Recommended output formats

For machine consumption, JSON is the preferred format. For both machine *and* human output in one run, pass `--format` multiple times:

```bash
patcherctl export --path=./reports --format=json --format=pdf
```

### What's not supported in non-interactive mode

- **`patcherctl reset creds`**: designed for keychain workflows. In CI, update the secrets and re-run.
- **`--fresh` setup flag**: non-interactive mode skips the setup state machine entirely; this flag has no effect.
- **UI configuration prompts**: PDF header/footer/logo use built-in defaults. If you need a customized PDF, configure UI settings on a workstation first and commit the resulting plist values to your CI image, or generate JSON in CI and style downstream.
