---
html_theme.sidebar_secondary.remove: True
---

(library-use)=

# Library Use

Patcher is a Python library as much as it is a CLI. Every CLI feature — fetching patch summaries, matching against Installomator labels, exporting reports — is built on top of the same public classes you can call directly from your own code.

## When to use Patcher as a library

- **Custom workflows.** Schedule fetches, pipe results into your own dashboards, or feed patch data into other tooling.
- **CI/CD pipelines.** Run reports headlessly in GitHub Actions, Jenkins, etc. without needing the macOS keychain or interactive setup.
- **Web services / APIs.** Embed Patcher into a FastAPI, Flask, or other ASGI service that exposes patch data programmatically.
- **One-off scripts.** Pull a quick device count, dump label matches to JSON, or anything else that's faster as a script than as a CLI invocation.

If you're administering a Jamf instance interactively from your Mac and just want PDF/Excel reports, the {ref}`CLI <usage>` is probably what you want instead.

* * *

::::{grid} 2
:class-container: sd-text-left
:gutter: 3
:margin: 2

:::{grid-item-card} {fas}`bolt;sd-text-primary`  Quickstart
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Install, authenticate, and make your first call.
```{toctree}
:caption: Quickstart
:maxdepth: 2
:hidden:

quickstart
```

+++
```{button-ref} library-quickstart
:ref-type: ref
:color: secondary
:expand:

Quickstart
```

:::

:::{grid-item-card} {fas}`code;sd-text-primary`  Common Patterns
:class-card: sd-card
:class-title: patcher-title
:shadow: md

Recipes for the most common library use cases.
```{toctree}
:caption: Common Patterns
:maxdepth: 2
:hidden:

recipes
```

+++
```{button-ref} library-recipes
:ref-type: ref
:color: secondary
:expand:

Common Patterns
```
:::

::::
