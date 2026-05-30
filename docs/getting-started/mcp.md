---
description: "Connect Claude Desktop, Claude Code, Cursor, or any Streamable HTTP MCP client to the Patcher catalog at mcp.patcherctl.dev. Query app coverage, drift, and details through natural language."
---

(patcher-mcp)=

# MCP Server

:::{rst-class} lead
Ask Claude (or any MCP-aware tool) about your patching catalog.
:::

---

Patcher includes a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server at `mcp.patcherctl.dev`. Once your AI client is connected, you can ask natural-language questions and the assistant calls Patcher on your behalf, returning structured catalog data inline.

As the catalog is public, no authentication is required.

:::{seealso}
The MCP server is just another method to query alongside the {doc}`REST API </reference/api/endpoints>` and the {class}`~patcher.clients.patcher_api.PatcherAPIClient` Python wrapper.
:::

## Connect your client

:::::{tab-set}
:sync-group: mcp-client

::::{tab-item} {iconify}`material-icon-theme:claude` Claude Code
:sync: claude-code

:::{code-block} console
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

## Verify it works

Whichever client you set up, the smoke test is asking it a Patcher-flavored question. If the assistant comes back with structured catalog data, you're connected.

## What you can ask

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

See the {doc}`MCP tools reference </reference/mcp/tools>` for full signatures, and {doc}`MCP recipes </guides/mcp-recipes>` for worked prompt examples.

### Example prompts

Some prompts that will reliably trigger a tool call.

:::{prompt}
What apps does Patcher track from Mozilla?
:::

:::{prompt}
Are there any apps with version drift across sources?
:::

:::{prompt}
:type: claude-code
Tell me about the latest Slack release.
:::

:::{prompt}
:type: claude-code
Summarize the Patcher catalog.
:::

If you see real data back, head over to {doc}`MCP recipes </guides/mcp-recipes>` for a deeper bench of useful prompts.

## Troubleshooting

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
