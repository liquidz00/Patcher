(support)=

# Troubleshooting

:::{rst-class} lead
Diagnose problems quickly: debug mode, exit codes, log interpretation, and the most common fixes.
:::

## Quick diagnostics

(exit-codes)=

### Exit codes

`patcherctl` uses specific exit codes so failures are easy to triage in scripts and CI:

| Exit code | Meaning |
|---|---|
| `0` | Success |
| `1` | Handled exception (PatcherError or user-facing issue) |
| `2` | Unhandled exception |
| `3` | Setup error |
| `4` | API error (e.g. unauthorized, invalid response) |
| `130` | KeyboardInterrupt (Ctrl+C) |

(debug)=

### Debug mode

Pass `--debug` (or `-x`) at the root level (*before* any subcommand) to show DEBUG-level logs on stdout in addition to the log file:

```console
$ patcherctl --debug export --path /path/to/save
```

Debug mode also suppresses the animated spinner so log lines don't fight for cursor position.

### `--help` / `-h`

Every command and subcommand supports both `--help` and `-h`:

```console
$ patcherctl --help
$ patcherctl export --help
```

(logs)=

## Interpreting Patcher logs

Logs land in `~/Library/Application Support/Patcher/logs`. Three files may exist:

| File | When it appears |
|---|---|
| `patcher.log` | Every `patcherctl` invocation |
| `patcher-agent.out.log` | stdout from the {ref}`LaunchAgent <launch_agent>` (if scheduled) |
| `patcher-agent.err.log` | stderr from the LaunchAgent |

Each log entry includes a timestamp, the {ref}`child logger <child-logger>` that wrote the line, and the level:

:::{card} Sample error
:class-card: sd-card

```text
2026-04-30 21:19:35,423 - Patcher.JamfClient - ERROR - Client error (401): [{'code': 'INVALID_TOKEN', 'description': 'Unauthorized', 'id': '0', 'field': None}]
```

The child logger here is {class}`~patcher.client.jamf.JamfClient`. **Include the child logger in bug reports**; it tells us which component raised the error.
:::

:::{card} Debug & info
:class-card: sd-card

```text
2026-05-01 16:35:31,697 - Patcher.Analyzer - DEBUG - Attempting to filter titles by FilterCriteria.OLDEST_LEAST_COMPLETE.
2026-05-01 16:35:31,704 - Patcher.Analyzer - INFO - Filtered 5 PatchTitles successfully based on FilterCriteria.OLDEST_LEAST_COMPLETE
```
:::

## Common fixes

When something goes wrong, it helps to separate **environment issues** (API credentials, network, TLS) from **configuration issues** (corrupt plist, stale cache, etc.).

### Update Patcher

The cheapest first move. Make sure you're on the latest release:

```console
$ python3 -m pip install --upgrade patcherctl
```

### Full reset

To rule out configuration drift, run a full reset. This wipes credentials, UI config, setup state, and cached data, then re-runs the setup wizard:

```console
$ patcherctl reset full
```

See {doc}`/usage/reset` for the granular alternatives.

:::{admonition} Known issue
:class: danger

If a previous setup attempt failed *after* the Jamf API role / client were created, a Standard re-run will fail with a `401` because those objects already exist on the Jamf side. Either retrieve the credentials from Keychain and switch to {ref}`SSO setup <setup_type>`, or delete the API role / client manually in Jamf and rerun.
:::

### Reinstall Patcher

If a full reset doesn't help, reinstall via `pip`:

```console
$ python3 -m pip uninstall patcherctl
$ python3 -m pip install patcherctl
```

:::{admonition} Optional
:class: admonition-optional
Before reinstalling, wipe the Application Support directory at `~/Library/Application Support/Patcher/` **except** the `logs` subdirectory. The logs help diagnose what caused the original problem.
:::

## TLS / corporate proxies

If your organization runs a TLS-inspecting proxy (Zscaler, Netskope, Cloudflare Gateway, Palo Alto GlobalProtect, etc.), Patcher should "just work" provided your corporate CA is installed in your operating system's native trust store. Most enterprise MDM deployments push this CA automatically.

Patcher uses [`truststore`](https://github.com/sethmlarson/truststore) to bridge Python's TLS stack to your OS's trust store:

| Platform | Trust source |
|---|---|
| macOS | Keychain (System + Login) |
| Windows | Certificate Store |
| Linux | `/etc/ssl/certs/ca-certificates.crt` |

You do **not** need to concatenate certificates into `certifi`'s `cacert.pem`, edit Python's `ssl` settings, or set `SSL_CERT_FILE`. If your browser can reach your Jamf Pro instance without a TLS warning, Patcher can too.

### Diagnosing TLS errors

If Patcher fails with an `APIResponseError: Network error fetching URL` and the underlying message mentions certificate verification:

1. **Verify the corporate CA is in your OS trust store:**
   - **macOS:** Keychain Access → System keychain → Certificates. Look for your company's root CA.
   - **Windows:** `certmgr.msc` → Trusted Root Certification Authorities → Certificates.
   - **Linux:** `ls /etc/ssl/certs/` or `trust list --filter=ca-anchors`.
2. **Confirm your MDM profile is fully applied.** New machines sometimes lack certificates until the next refresh.
3. **If the CA is installed but the error persists**, get in touch ([Submit an issue](#submit-an-issue) or the MacAdmins Slack `#patcher` channel) with the full error output and any details about installed security software.

## Still stuck?

### Submit an issue

The fastest path to support is filing an [issue on GitHub](https://github.com/liquidz00/Patcher/issues/new/choose). Include as many details as possible: what you ran, what you expected, the full error output, the child logger from the log entry, and what troubleshooting steps you've already tried.

### MacAdmins Slack

We try to stay active in the `#patcher` channel on MacAdmins Slack ([join here](https://macadmins.slack.com/archives/C07EH1R7LB0)). Despite full-time jobs, we'll do our best to respond.
