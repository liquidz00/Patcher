---
layout: focused
description: "Patcher reference: Python library entry points, the REST API surface, data shapes, building blocks, helper classes, and CLI internals. Grouped by reader intent."
---

# Reference

:::{rst-class} lead
Patcher's entry points, API surface, models and more.
:::

---

Auto-generated API reference, grouped by what you're trying to do, not where the file lives. If you're looking for a `patcherctl` flag or subcommand, those are documented inline on the relevant {doc}`Usage page </guides/usage/cli>`.

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Library Classes`
:link: library/index
:link-type: doc

The four classes most callers import. Each one owns one external surface (Jamf, the Patcher catalog API, the Installomator label registry) or composes the others ({class}`~patcher.core.patcher_client.PatcherClient`).
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `REST API`
:link: api/index
:link-type: doc

The public catalog at `api.patcherctl.dev`. Any-language consumers and shell scripts call it directly; Python consumers should reach for {class}`~patcher.clients.patcher_api.PatcherAPIClient` instead, which wraps the same endpoints with typed responses.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `MCP Server`
:link: mcp/index
:link-type: doc

The Model Context Protocol surface at `mcp.patcherctl.dev`. Five tools for querying the catalog from Claude, Cursor, Claude Code, and any other Streamable HTTP MCP client. See {doc}`/guides/usage/agents` for client setup.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Data Models`
:link: models/index
:link-type: doc

Pydantic models returned by the entry-point clients. These are what you destructure in your own code: iterate a list of `PatchTitle`, inspect a `Label`, render a `UIConfig`.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Building Blocks`
:link: building-blocks/index
:link-type: doc

Stable, less commonly imported. Reach for these when you're extending Patcher (custom HTTP transport, alternate config source, embedded analysis) rather than just using it.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `Helper Classes`
:link: helpers/index
:link-type: doc

Utility classes Patcher uses across the codebase: structured logging and the exception hierarchy.
:::

:::{grid-item-card} {iconify}`octicon:arrow-up-right-16` `CLI Internals`
:link: internals/index
:link-type: doc

Implementation detail of `patcherctl`. Not part of the library's stable surface; documented for contributors who are reading or modifying the CLI.
:::
::::

```{toctree}
:hidden:

library/index
api/index
mcp/index
models/index
building-blocks/index
helpers/index
internals/index
```
