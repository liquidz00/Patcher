---
description: "Worked prompt examples for the Patcher MCP server: catalog-wide questions, single-app drilldowns, drift audits, and search queries."
---

(mcp-recipes)=

# MCP Recipes

:::{rst-class} lead
Prompts that show what the Patcher MCP server can do.
:::

---

Five tools, lots of useful questions. This page groups example prompts by intent so you can crib whichever match your workflow. The assistant picks the right tool based on phrasing; you don't have to invoke them by name.

For setup, see {doc}`/getting-started/mcp`. For full tool signatures, see {doc}`/reference/mcp/tools`.

## Catalog-wide questions

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

Behind the scenes these call `get_catalog_summary` or `list_categories` — both return small, cheap structured payloads the assistant can describe in prose.

## Single-app drilldowns

When you know (or roughly know) the app and want the full record.

:::{prompt}
What's the latest version of Slack?
:::

:::{prompt}
Show me the full Patcher record for 1Password 8.
:::

:::{prompt}
What's the download URL for the latest Firefox build?
:::

These call `get_app` once the slug is known, or `search_apps` first if the assistant needs to disambiguate (e.g. multiple Firefox slugs: `firefox`, `firefoxesr`, `firefoxpkg`).

## Drift and quality audits

The most uniquely-Patcher question: do upstream sources agree on the latest version?

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

## Search and exploration

When you only have a partial app name, or want to compare a few apps.

:::{prompt}
Find me apps with "office" in the name.
:::

:::{prompt}
What apps does Patcher track from Microsoft?
:::

:::{prompt}
Search the catalog for anything matching "vsc".
:::

Backed by `search_apps`, which matches case-insensitively against slug, name, vendor, and bundle ID.

## Chained questions

The assistant happily calls multiple tools in one turn when a question requires it. A prompt like the one below first calls `search_apps` to find Mozilla apps, then `list_drift` filtered to that vendor.

:::{prompt}
For every Mozilla app in the catalog, tell me whether sources agree on the latest version.
:::

:::{prompt}
Find Adobe apps and show me which ones have version drift.
:::

This is where MCP earns its keep relative to the REST API or the Python client: you describe the goal, the assistant picks the tools and orchestrates the calls. No glue code to maintain.

## Working in Claude Code

If you've connected the MCP server inside a Claude Code session in this repo, the catalog is one prompt away from any other work. Patcher contributors find this especially useful when adding tests or debugging matching:

:::{prompt}
:type: claude-code
Show me everything Patcher knows about Sublime Text
:::

:::{prompt}
:type: claude-code
List apps where my Installomator label is silently behind Homebrew Cask
:::
