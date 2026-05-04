(ci-cd)=

# CI/CD & Non-Interactive Mode

Patcher can run without prompts in environments where the macOS keychain isn't
available and where persistent state isn't desired — typically GitHub Actions
runners, Linux build agents, and other ephemeral CI/CD contexts.

## How non-interactive mode works

When all three of the following are provided — via CLI flags **or** environment
variables — Patcher engages non-interactive mode:

| CLI flag | Environment variable | Description |
|---|---|---|
| `--client-id` | `PATCHER_CLIENT_ID` | Jamf Pro API client ID |
| `--client-secret` | `PATCHER_CLIENT_SECRET` | Jamf Pro API client secret |
| `--url` | `PATCHER_URL` | Jamf Pro instance URL |

CLI flags take precedence over environment variables. Mix-and-match is fine
(e.g. URL via env var, secrets via flag).

In non-interactive mode, Patcher:

- **Holds credentials in memory only** for the lifetime of the invocation.
  The macOS keychain is never read or written.
- **Skips every interactive prompt** — setup type, Installomator support, and
  the UI configuration (PDF header/footer/logo) are all bypassed.
- **Does not persist setup completion** to disk. The next invocation must
  provide credentials again, which is the desired behavior on ephemeral runners.
- **Runs the requested subcommand immediately** after fetching an access token.

## Quick example

```bash
# All three credentials via flags
patcherctl \
  --client-id="abc-123" \
  --client-secret="my-secret" \
  --url="https://my.jamfcloud.com" \
  export --path=/tmp/reports --format=json

# Or via environment variables
export PATCHER_CLIENT_ID=abc-123
export PATCHER_CLIENT_SECRET=my-secret
export PATCHER_URL=https://my.jamfcloud.com
patcherctl export --path=/tmp/reports --format=json
```

## GitHub Actions example

A complete workflow that runs Patcher daily and uploads the JSON report as a
build artifact. Adjust the schedule, output path, and artifact retention to
suit your needs.

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
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
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

      - name: Upload report artifact
        uses: actions/upload-artifact@v4
        with:
          name: patch-report
          path: ./reports/*.json
          retention-days: 30
```

The JSON output is well-suited to downstream automation — feed it into another
job that posts to Slack, ingests into a dashboard, or triggers patching policies
based on coverage thresholds.

## Security considerations

- **Never commit credentials to your repository.** Use GitHub Secrets (or the
  equivalent on your CI platform) for `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET`,
  and `JAMF_URL`.
- **Use a dedicated API client.** Create a separate Jamf Pro API client/role
  for CI/CD with the minimum privileges Patcher needs. See
  {ref}`Creating an API Role/Client <api-creation>` for details.
- **Rotate credentials periodically.** Treat the client secret like any other
  long-lived credential.

## Recommended output formats

For machine-consumable pipelines, JSON is the preferred format:

```bash
patcherctl export --path=./reports --format=json
```

The JSON output is structured around a `PatchTitle` schema and includes a
`generated_at` timestamp, the report title, the title count, and the full list
of titles with completion percentages. See {ref}`Export <export>` for the
full format reference.

If you need both JSON (for automation) and PDF (for humans), pass `--format`
multiple times:

```bash
patcherctl export --path=./reports --format=json --format=pdf
```

## What's not supported in non-interactive mode

- **Resetting credentials** (`patcherctl reset creds`) — designed for keychain
  workflows. In CI you simply update the secrets and re-run.
- **`--fresh` setup flag** — non-interactive mode skips the setup state machine
  entirely; this flag has no effect.
- **UI configuration prompts** — PDF header/footer text and custom logos use
  built-in defaults. If you need a customized PDF, configure UI settings on a
  workstation first and commit the resulting plist values, or generate JSON in
  CI and produce styled PDFs downstream.
