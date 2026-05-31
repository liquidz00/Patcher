---
layout: focused
description: "The commands that power Patcher -- a high level overview of export, analyze, reset, diff, and drift."
---

# Usage

:::{rst-class} lead
The underlying commands that drive Patcher.
:::

---

::::{grid} 1 2 2 2
:gutter: 2
:padding: 0
:class-row: surface

:::{grid-item-card} Export

Pull patch data out of Jamf and write it as Excel, PDF, HTML, and JSON reports you can share. Reach for it whenever you need a shareable snapshot of fleet patch coverage.

+++
{iconify}`material-icon-theme:python` [Library](library.md#export) {iconify}`mdi:bash` [CLI](cli.md#export)
:::

:::{grid-item-card} Analyze

Filter, rank, and trend patch data to surface the titles that need attention, either against a single report or across every cached dataset over time. Reach for it to answer "which titles are lagging?"

+++
{iconify}`material-icon-theme:python` [Library](library.md#analyze) {iconify}`mdi:bash` [CLI](cli.md#analyze)
:::

:::{grid-item-card} Reset

Restore Patcher's persisted state granularly: credentials, UI configuration, cached data, or all of it. Reach for it to fix a typo'd credential, clear the cache, or start over with the setup wizard.

+++
{iconify}`material-icon-theme:python` [Library](library.md#reset) {iconify}`mdi:bash` [CLI](cli.md#reset)
:::

:::{grid-item-card} Diff

Compare patch state between two points in time to see what was added, removed, or changed. Reach for it to keep a paper trail of every patch-coverage shift between two specific moments.

+++
{iconify}`material-icon-theme:python` [Library](library.md#diff) {iconify}`mdi:bash` [CLI](cli.md#diff)
:::

:::{grid-item-card} Drift

Find apps where upstream sources disagree on what "latest" means, the strongest signal that a label has silently fallen behind. Reach for it as a low-cost canary for stuck upstream sources.

+++
{iconify}`material-icon-theme:python` [Library](library.md#drift) {iconify}`mdi:bash` [CLI](cli.md#drift)
:::
::::

```{toctree}
:hidden:

library
cli
api
agents
```
