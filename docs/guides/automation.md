---
description: "Run Patcher unattended via launchd or in CI. Covers non-interactive mode, keyring-backend behavior on non-macOS runners, and a GitHub Actions example."
---

# Automating Patcher

:::{rst-class} lead
Running Patcher on a schedule with `launchd` or in CI/CD pipelines.
:::

---

Two patterns cover most automation needs: a `launchd` LaunchAgent on a workstation for time-of-day scheduling, or non-interactive invocations on ephemeral runners (GitHub Actions, Linux build agents, anything without a keychain).

## Scheduling locally with `launchd`

(launch_agent)=

For a workstation that runs Patcher on a schedule, a `launchd` LaunchAgent is the cleanest option. It hands the scheduling off to macOS and writes stdout/stderr to log files you can tail when something misbehaves.

:::{warning}
Make sure both `python3` and `patcherctl` are on your `PATH`. When you install via PyPI, `patcherctl` lands in your Python user-base `bin` directory. See {ref}`add-path` if `patcherctl --version` fails to resolve.
:::

::::{steps}
:::{step} Build the property list file
Customize the example `.plist` below to fit your needs. Specifically, be sure to adjust paths and flags under `ProgramArguments` to match what you'd run by hand. `StartCalendarInterval` configures the schedule the agent will run. Reference [Launched](https://launched.zerowidth.com/) as it is a great helper for building these.

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

To ensure the LaunchAgent is working:

::::{steps}

:::{step} Manually run the export command.

Manually run the ``patcherctl export`` command to confirm it executes as expected.
:::

:::{step} Check the logs.

Check the logs for errors or confirmation of success:

- **Standard Output**: ``~/Library/Application Support/Patcher/logs/patcher-agent.out.log``
- **Standard Error**: ``~/Library/Application Support/Patcher/logs/patcher-agent.err.log``
:::

::::

(ci-cd)=

## CI/CD & non-interactive mode

For ephemeral environments (GitHub Actions runners, Linux build agents, etc.), Patcher can run in **non-interactive mode**. The same mode {class}`PatcherClient <patcher.core.patcher_client.PatcherClient>` engages when library callers pass `client_id`, `client_secret`, and `server` directly. No keychain access, no setup wizard, no persistent state.

### Engaging non-interactive mode

:::{note}
Credentials can be set via command line flags **or** environment variables. If both are used, command line flags take precedence.
:::

| CLI flag | Environment variable | Description |
|---|---|---|
| `--client-id` | `PATCHER_CLIENT_ID` | Jamf Pro API client ID |
| `--client-secret` | `PATCHER_CLIENT_SECRET` | Jamf Pro API client secret |
| `--url` | `PATCHER_URL` | Jamf Pro instance URL |

#### Important considerations

In non-interactive mode, Patcher:

::::{highlights}
{iconify}`octicon:key-16` Memory-only credentials
: Credentials are held in memory for the lifetime of the invocation. The macOS keychain is never read or written. Right for ephemeral runners and Docker containers where there's no persistent secret store anyway.

{iconify}`octicon:skip-16` Skips every interactive prompt
: Setup type, Installomator support, and UI configuration are all bypassed. Any code path that would normally pause for input proceeds with sane defaults instead.

{iconify}`octicon:repo-deleted-16` No completion persistence
: Setup completion is not written to disk. The next invocation must provide credentials again, which is exactly what you want on ephemeral runners that wipe their filesystem between jobs.

{iconify}`octicon:zap-16` Runs immediately
: The requested subcommand executes as soon as an access token is fetched. No wizard, no prompts, no waiting.
::::

(linux-keyring)=

### Linux runners: keyring backend

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

Library callers benefit from one additional advantage: arbitrary transforms between `fetch_patches()` and `export()` (filter to a subset, decorate titles, push to multiple destinations) without piping through the CLI's output formats. No environment-variable dance is required: importing `patcher` installs the null `keyring` backend on non-macOS platforms automatically (see [Linux runners: keyring backend](#linux-runners-keyring-backend) above), and library callers that pass `client_id` / `client_secret` / `server` directly to `PatcherClient(...)` bypass the keyring entirely regardless of platform. Set `KEYRING_BACKEND` only if you specifically want a different backend than the null default.

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
