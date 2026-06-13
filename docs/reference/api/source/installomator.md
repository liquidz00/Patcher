---
description: "Reference for patcher_api.installomator — bash-fragment parser, dynamic-value resolver, and ingest entry for Installomator labels."
---

# installomator

The Installomator subsystem is co-located in its own subpackage. Three modules:

::::{markers}
:icon: octicon:code-16

:::{marker} parser
Tokenizes Installomator's bash label fragments into structured field assignments without invoking a shell.
:::

:::{marker} resolver
Evaluates dynamic field values (e.g. `downloadURL=$(curl ... | grep ...)`) inline where possible, in subprocess as an opt-in fallback. For the two-stage split with the macOS runner see {doc}`/project/architecture/resolution`.
:::

:::{marker} ingest
Pulls the Installomator label registry from GitHub and writes parsed/resolved rows into the catalog.
:::
::::

## Parser

The fragment parser now lives in the shared library package (`patcher.catalog._fragment_parser`); the API ingest imports it.

```{eval-rst}
.. autofunction:: patcher.catalog._fragment_parser.parse_fragment
```

## Resolver

The resolver returns one of three outcomes (`Resolved`, `Unresolvable`, `InvalidOutput`) so callers can distinguish a clean value from a rejected one from nothing at all.

```{eval-rst}
.. autoclass:: patcher_api.installomator.resolver.Resolved
   :members:

.. autoclass:: patcher_api.installomator.resolver.Unresolvable
   :members:

.. autoclass:: patcher_api.installomator.resolver.InvalidOutput
   :members:

.. autoclass:: patcher_api.installomator.resolver.PipelineResolver
   :members:

.. autofunction:: patcher_api.installomator.resolver.resolve

.. autofunction:: patcher_api.installomator.resolver.is_shell_expression

.. autofunction:: patcher_api.installomator.resolver.looks_like_clean_http_url

.. autofunction:: patcher_api.installomator.resolver.looks_like_clean_version
```

## Ingest

```{eval-rst}
.. autoclass:: patcher_api.installomator.ingest.FetchPlan
   :members:

.. autofunction:: patcher_api.installomator.ingest.set_resolve_on_ingest
```
