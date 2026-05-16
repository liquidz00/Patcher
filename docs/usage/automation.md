# Automation

:::{rst-class} lead
Run Patcher unattended, either locally on a schedule with `launchd` or in CI/CD pipelines.
:::

Patcher is designed to run unattended: on a workstation via `launchd`, in CI/CD pipelines, or anywhere else that needs scheduled patch reports. This page covers both patterns.

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

For ephemeral environments (GitHub Actions runners, Linux build agents, etc.), Patcher runs in **non-interactive mode**. No keychain access, no setup wizard, no persistent state.

### Engaging non-interactive mode

Provide all three credentials via CLI flags **or** environment variables (mix-and-match is fine; flags take precedence):

| CLI flag | Environment variable | Description |
|---|---|---|
| `--client-id` | `PATCHER_CLIENT_ID` | Jamf Pro API client ID |
| `--client-secret` | `PATCHER_CLIENT_SECRET` | Jamf Pro API client secret |
| `--url` | `PATCHER_URL` | Jamf Pro instance URL |

In non-interactive mode, Patcher:

- **Holds credentials in memory only** for the lifetime of the invocation. The macOS keychain is never read or written.
- **Skips every interactive prompt.** Setup type, Installomator support, and UI configuration are all bypassed.
- **Does not persist setup completion** to disk. The next invocation must provide credentials again, which is exactly what you want on ephemeral runners.
- **Runs the requested subcommand immediately** after fetching an access token.

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
