---
description: "Diagnose Patcher with debug logging and exit codes, and fix the common failures: command-not-found, authentication errors, certificate issues, and stale report data."
---

# Troubleshooting

:::{rst-class} lead
When Patcher misbehaves, turn on debug logging, then jump to your symptom.
:::

---

## Debug Logging

(debug)=

Every command takes a root-level `--debug` (or `-x`), placed *before* the subcommand. It streams DEBUG-level logs to your terminal and hides the spinner so they stay readable.

```{code-block} bash
:caption: Run any command with verbose output

$ patcherctl --debug export --path ~/reports
```

Those logs are written to `~/Library/Application Support/Patcher/logs/patcher.log` with or without `--debug`. Attach that file when you report a bug.

## Exit Codes

(exit-codes)=

`patcherctl` returns a distinct code per failure class, so CI and scripts can branch on it.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Handled error (a `PatcherError` or user-facing issue) |
| `2` | Unhandled exception |
| `3` | Setup error |
| `4` | API error, such as an unauthorized or invalid response |
| `130` | Interrupted with Ctrl+C |

## Command Not Found

If `patcherctl --version` comes back with `command not found`, the package installed fine but landed outside your shell's `PATH`. Adding your Python user-base `bin` directory fixes it, covered on the install page under {ref}`add-path`.

## Authentication Failures

A `401` or `403` from Jamf means the stored credentials are missing a privilege, expired, or simply wrong. Re-run the wizard with `patcherctl --fresh` to re-enter them, or do a {ref}`full reset <full-reset>` to clear everything and start over.

:::{admonition} Known Issue
:class: danger

If a Standard setup failed *after* it created the Jamf API role and client, the next Standard run also fails with a `401`, because those objects already exist. Delete the role and client in Jamf and retry, or switch to {ref}`SSO setup <setup_type>` to reuse what Patcher already created.
:::

(support)=

## Certificate Errors

Patcher trusts whatever your Mac trusts. On a network behind a TLS-inspecting proxy (Zscaler, Netskope, Palo Alto GlobalProtect, and the like), it works as long as your company's certificate is in the system keychain, which your MDM usually installs for you. If your browser can reach Jamf without a security warning, Patcher can too. The {ref}`SSL verification <ssl-verify>` section on the install page has the background.

When Patcher fails with a network error that mentions certificate verification, two checks cover almost every case.

::::{steps}

:::{step} Confirm the company certificate is installed
In Keychain Access, look under the System keychain for your organization's root certificate authority.
:::

:::{step} Confirm the MDM profile has applied
A newly enrolled Mac sometimes lacks the certificate until its next check-in.
:::
::::

## Empty or Stale Data

When a report is missing data or looks out of date, it's usually one of these.

::::{markers}

:::{marker} Every title has an empty `install_label`
:icon: octicon:unlink-16
Installomator matching is switched off. Turn it back on per {ref}`disabling_installomator_support`.
:::

:::{marker} The numbers look out of date
:icon: octicon:history-16
Analysis reads the most recent cached report. Clear the cache with `patcherctl reset cache`, then re-run to pull fresh data from Jamf.
:::
::::

(full-reset)=

## Start Over

A full reset wipes credentials, UI configuration, setup state, and cached data, then re-runs the wizard. It's the fastest way to rule out a corrupt local state.

```{code-block} bash
:caption: Wipe all local state and re-run setup

$ patcherctl reset full
```

If a reset doesn't help, reinstall the package.

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:uv` uv
```bash
$ uv pip install --reinstall patcherctl
```
:::

:::{tab-item} {iconify}`material-icon-theme:python` pip
```bash
$ python3 -m pip install --force-reinstall patcherctl
```
:::

::::

## Still Stuck?

File a [GitHub issue](https://github.com/liquidz00/Patcher/issues/new/choose) with the command you ran, the full error output, and your `patcher.log`. For a back-and-forth, the maintainers are in the [`#patcher` channel](https://macadmins.slack.com/archives/C07EH1R7LB0) on MacAdmins Slack.
