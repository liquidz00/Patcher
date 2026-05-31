---
description: "Drive Patcher from an AI agent: connect the MCP server for natural-language catalog queries, browse worked prompt recipes, or use the bundled Claude Code skill for cross-source app lookups."
---

(agent-guides)=

# Working with Agents

:::{rst-class} lead
Two ways to put Patcher in front of an AI assistant.
:::

---

Patcher meets agents on two surfaces. The server exposes the public catalog over the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) so that Claude (Code & Desktop), Cursor, or any MCP-aware client can query app coverage through natural language. The [Claude Code skill](#claude-code-skill) is a bundled slash command that looks up a Mac app across catalog sources, and vendor docs in one shot.

(patcher-mcp)=

## MCP server

Connect your AI clients to the server at `mcp.patcherctl.dev`. Once connected, you can ask natural-language questions and the assistant calls Patcher on your behalf, returning structured catalog data inline.

As the catalog is public, no authentication is required.

:::{seealso}
The MCP server is just another method to query alongside the {doc}`REST API </reference/api/endpoints>` and the {class}`~patcher.clients.patcher_api.PatcherAPIClient` Python wrapper.
:::

### Connect your client

:::::{tab-set}
:sync-group: mcp-client

::::{tab-item} {iconify}`material-icon-theme:claude` Claude Code
:sync: claude-code

:::{code-block} bash
:caption: Automatically creates .mcp.json in project directory
$ claude mcp add --transport http patcher https://mcp.patcherctl.dev/mcp
:::

:::{note}
If you want Patcher available in every Claude Code session, pass the `--scope user` flag.
:::

::::

::::{tab-item} {iconify}`material-icon-theme:claude` Claude Desktop
:sync: claude-desktop

:::{code-block} json
:caption: Add to ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "patcher": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.patcherctl.dev/mcp"]
    }
  }
}
:::

Fully quit Claude Desktop (Cmd-Q) and reopen. The Patcher tools appear in the {iconify}`octicon:tools-16` menu next to the input box.

::::

::::{tab-item} {iconify}`material-icon-theme:cursor` Cursor
:sync: cursor

:::{code-block} json
:caption: Add to ~/.cursor/mcp.json
{
  "mcpServers": {
    "patcher": {
      "url": "https://mcp.patcherctl.dev/mcp"
    }
  }
}
:::

Restart Cursor or use **Refresh** in the MCP panel to load the new server.
::::
:::::

### Verify it works

Smoke-test the connection by asking a Patcher-flavored question. Structured catalog data back means you're connected; if not, see [Troubleshooting](#troubleshooting).

### What you can ask

You don't need to call these tools by name, your AI client picks the right one automatically based on your question.

Get a catalog summary
: Top-line stats. Total apps and per-source coverage counts.

Search apps
: Fuzzy lookup across slug, name, vendor, and bundle ID.

Get a specific app
: The full record for one app (versions, sources, download URL, installation method).

Listing drift
: Apps where upstream sources disagree on the latest version.

List categories
: Distinct install methods, sources, and vendors present in the catalog.

See the {doc}`MCP tools reference </reference/mcp/tools>` for full signatures, and [MCP recipes](#mcp-recipes) for worked prompt examples.

### Troubleshooting

If the tools don't appear after configuring:

::::::{steps}

:::::{step} Check server health
```{code-block} bash
$ curl -sS https://mcp.patcherctl.dev/health
```
Should return `{"status":"ok"}`. If it does not, the catalog itself is unreachable. If it does, the server is up and running and the issue is client-side.
:::::

:::::{step} Check your agents

::::{tab-set}

:::{tab-item} {iconify}`material-icon-theme:claude` Claude Code

`claude mcp list` confirms whether the server is registered.
<br>Re-run `claude mcp add` if it's missing.
:::

:::{tab-item} {iconify}`material-icon-theme:claude` Claude Desktop

Fully quit (`CMD+Q`, not just close the window) and reopen.
<br>The MCP config is read once at launch.
:::

:::{tab-item} {iconify}`material-icon-theme:cursor` Cursor

The MCP panel has a Refresh control.
<br>Restart Cursor if it still doesn't appear.
:::

::::
:::::

:::::{step} Check debugging logs
```{code-block} bash
$ fastmcp list https://mcp.patcherctl.dev/mcp --transport http --auth none
```

For deeper protocol-level debugging, speak MCP directly and surface any handshake errors verbatim.
:::::
::::::

(mcp-recipes)=

## MCP recipes

Five tools, lots of useful questions. This section groups example prompts by intent so you can crib whichever match your workflow. The assistant picks the right tool based on phrasing; you don't have to invoke them by name.

For full tool signatures, see {doc}`/reference/mcp/tools`.

### Catalog-wide questions

Top-level reads when you want to know what Patcher knows or which sources cover what.

:::{prompt}
Summarize the Patcher catalog.
:::

:::{prompt}
Which install methods are represented in the catalog?
:::

:::{prompt}
How many apps does Patcher track from Mozilla?
:::

These call `get_catalog_summary` or `list_categories`.

### Single-app drilldowns

When you know (or roughly know) the app and want the full record.

:::{prompt}
:type: claude-code
What's the latest version of Slack?
:::

:::{prompt}
:type: claude-code
Show me the full Patcher record for 1Password 8.
:::

:::{prompt}
:type: claude-code
What's the download URL for the latest Firefox build?
:::

These call `get_app`, or `search_apps` first to disambiguate (e.g. `firefox`, `firefoxesr`, `firefoxpkg`).

### Drift and quality audits

Do upstream sources agree on the latest version?

:::{prompt}
Are there any apps with version drift across sources?
:::

:::{prompt}
Show me drift for Mozilla apps specifically.
:::

:::{prompt}
Which apps have Installomator and Homebrew Cask disagreeing on what's latest?
:::

Backed by `list_drift`, which can filter by vendor or by which source must have participated in the disagreement. Useful for triaging "did this label fall behind upstream?" without scanning the full catalog by hand. For the underlying mental model, see {doc}`/project/pipelines/resolution`.

### Search and exploration

When you only have a partial app name, or want to compare a few apps.

:::{prompt}
:type: claude-code
Find me apps with "office" in the name.
:::

:::{prompt}
:type: claude-code
What apps does Patcher track from Microsoft?
:::

:::{prompt}
:type: claude-code
Search the catalog for anything matching "vsc".
:::

Backed by `search_apps`, which matches case-insensitively against slug, name, vendor, and bundle ID.

### Chained questions

The assistant happily calls multiple tools in one turn when a question requires it. A prompt like the one below first calls `search_apps` to find Mozilla apps, then `list_drift` filtered to that vendor.

:::{prompt}
For every Mozilla app in the catalog, tell me whether sources agree on the latest version.
:::

:::{prompt}
Find Adobe apps and show me which ones have version drift.
:::

This is where MCP earns its keep relative to other methods of Patcher use. Describe the goal and the assistant picks the tools and orchestrates the calls.

### Working in Claude Code

If you've connected the MCP server inside a Claude Code session in this repo, the catalog is one prompt away from any other work. It's especially useful when adding tests or debugging matching.

:::{prompt}
:type: claude-code
Show me everything Patcher knows about Sublime Text
:::

:::{prompt}
:type: claude-code
List apps where my Installomator label is silently behind Homebrew Cask
:::

(claude-code-skill)=

## Patcher skill

Patcher ships a [Claude Code](https://claude.com/claude-code) skill alongside the repository. It's a read-only lookup utility that takes an app name, checks {doc}`catalog sources </project/sources>`, and pulls vendor and Jamf deployment documentation into one report. No database writes, no Jamf access required.

### Install

The skill lives in the Patcher repo, so contributors who clone Patcher already have it. To make the skill available across every Claude Code session regardless of working directory, copy it into your user-level skills directory.

```bash
$ mkdir -p ~/.claude/skills
$ cp -R /path/to/Patcher/.claude/skills/patcher ~/.claude/skills/
```

:::{note}
The Installomator matching step calls `uv run python` with `rapidfuzz`. Either run user-scoped invocations from inside a project that has `rapidfuzz` available, or install it on a system Python that `uv run` falls back to.
:::

### Usage

Pass the name of the app to the skill. The app name will be normalized (lowercased, whitespace stripped and dots removed) before matching but preserves the original form in the report.

:::{prompt}
:type: claude-code

/patcher Google Chrome
:::

:::{prompt}
:type: claude-code

/patcher "Cisco AnyConnect Secure Mobility Client"
:::


:::{code-block} text
:caption: Sample output for a well-covered app (Slack)

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
:::

The Installomator section uses three confidence flags:

| Score | Flag | Meaning |
|---|---|---|
| `100` | exact | Direct or normalized hit on the label name |
| `85`–`99` | high conf | Above Patcher's default matching threshold, would auto-match |
| `75`–`84` | below threshold | Surfaced for visibility, would NOT be picked up automatically |

### Limitations

- **AutoPkg fallback is org-scoped.** When local `autopkg search` isn't available, the skill falls back to a GitHub code search across the `autopkg/` org only. Community recipes outside that org won't surface.
- **Web search filters aggressively.** The Deployment docs section prefers vendor admin docs, `learn.jamf.com`, and `community.jamf.com` accepted solutions. Blog posts and YouTube tutorials are rejected by design. If nothing high-quality surfaces, the section reports `(no official deployment docs surfaced)` rather than fabricating links.
- **Not a version source.** For current versions and install commands, use the `patcherctl` CLI or {class}`~patcher.clients.patcher_api.PatcherAPIClient` against `api.patcherctl.dev`.
