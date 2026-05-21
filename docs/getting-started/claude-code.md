---
description: "Use Patcher's bundled Claude Code skill to look up Mac apps across Installomator, Homebrew Cask, AutoPkg, and vendor deployment docs with one slash command."
---

(claude-code-skill)=

# Claude Code skill

:::{rst-class} lead
Use Patcher within Claude Code sessions.
:::

---

Patcher ships a [Claude Code](https://claude.com/claude-code) skill at `.claude/skills/patcher/`. It's a read-only lookup utility: given an app name, it checks Installomator, Homebrew Cask, and AutoPkg in parallel, surfaces a Jamf App Installer placeholder (the catalog endpoint requires tenant access, so the skill reports "skipped" with a pointer to the public JAI catalog), and pulls vendor and Jamf deployment documentation into one report. No database writes, no Jamf access required.

It's useful when you're:

- Adding a new app to your patch tracking and want to know which deployment paths exist before you pick one.
- Debugging a Patcher unmatched-title to see whether the app exists under a different slug in one of the upstream catalogs.
- Triaging "can we deploy X" without leaving the terminal.

## Install

The skill lives in the Patcher repo, so contributors who clone Patcher already have it.

:::::{tab-set}

::::{tab-item} {iconify}`material-icon-theme:folder-content` Project-scoped (recommended)
:sync: project

If you've already cloned Patcher and run `make dev`, the skill is in place and Claude Code picks it up automatically when you invoke it from the Patcher repo root.

```{code-block} console
$ cd ~/path/to/Patcher
$ claude
...
──────────────────────────────────────────────────────────────────────
❯ /patcher Slack
──────────────────────────────────────────────────────────────────────
  ? for shortcuts · ← for agents  
```

::::

::::{tab-item} {iconify}`material-icon-theme:folder-utils` User-scoped
:sync: user

To make the skill available across every Claude Code session regardless of working directory, copy it into your user-level skills directory:

```{code-block} console
$ mkdir -p ~/.claude/skills
$ cp -R /path/to/Patcher/.claude/skills/patcher ~/.claude/skills/
```

The Installomator matching step calls `uv run python` with `rapidfuzz`. Either run user-scoped invocations from inside a project that has `rapidfuzz` available, or install it on a system Python that `uv run` falls back to.

::::
:::::

## Usage

One required argument: the app name. The skill normalizes (lowercase, strip spaces and dots) before matching but preserves the original form in the report.

```{code-block} console
/patcher Google Chrome
/patcher 1Password
/patcher Zoom
/patcher "Cisco AnyConnect Secure Mobility Client"
```

Sample output for a well-covered app:

```{code-block} text
App: Slack
─────────────────────────────────────────────────────────────

Installomator
  slack                                    score 100  (direct, exact)

Homebrew Cask
  slack                                    v4.42.117

AutoPkg
  autopkg/recipes/Slack/Slack.download.recipe       (source: local)
  autopkg/recipes/Slack/Slack.pkg.recipe            (source: local)

Jamf App Installer
  skipped (no Jamf access). Browse public catalog at:
  https://learn.jamf.com/r/en-US/jamf-app-catalog/App_Installers_Software_Titles

Deployment docs
  Slack — Manage Slack at your organization
    https://slack.com/help/articles/115004629603
```

The Installomator section uses three confidence flags:

| Score | Flag | Meaning |
|---|---|---|
| `100` | exact | Direct or normalized hit on the label name |
| `85`–`99` | high conf | Above Patcher's default matching threshold, would auto-match |
| `75`–`84` | below threshold | Surfaced for visibility, would NOT be picked up automatically |

## Limitations

- **No Jamf App Installer coverage.** The undocumented JAI titles endpoint requires Jamf Pro tenant access, which the skill doesn't assume. The output instead points to the public JAI catalog browser.
- **AutoPkg fallback is org-scoped.** When local `autopkg search` isn't available, the skill falls back to a GitHub code search across the `autopkg/` org only. Community recipes outside that org won't surface.
- **Web search filters aggressively.** The Deployment docs section prefers vendor admin docs, `learn.jamf.com`, and `community.jamf.com` accepted solutions. Blog posts and YouTube tutorials are rejected by design. If nothing high-quality surfaces, the section reports `(no official deployment docs surfaced)` rather than fabricating links.
- **Read-only.** The skill doesn't propose or write canonical-app-DB entries. That's intentional; it's a lookup utility, not an ingest tool.
- **Not a version source.** For current versions, install commands, and CVE data, use the `patcherctl` CLI or {class}`~patcher.clients.patcher_api.PatcherAPIClient` against `api.patcherctl.dev`.
