---
description: "Reference for patcher_api.installomator — bash-fragment parser, dynamic-value resolver, and ingest entry for Installomator labels."
---

# installomator

The Installomator subsystem is co-located in its own subpackage. Three modules:

- **parser**: tokenizes Installomator's bash label fragments into structured field assignments without invoking a shell.
- **resolver**: evaluates dynamic field values (e.g. `downloadURL=$(curl ... | grep ...)`) inline where possible, in subprocess as an opt-in fallback. For the producer/consumer split with the macOS runner see {doc}`/project/pipelines/resolution`.
- **ingest**: pulls the Installomator label registry from GitHub and writes parsed/resolved rows into the catalog.

## Parser

```{eval-rst}
.. automodule:: patcher_api.installomator.parser
   :members:
```

## Resolver

```{eval-rst}
.. automodule:: patcher_api.installomator.resolver
   :members:
```

## Ingest

```{eval-rst}
.. automodule:: patcher_api.installomator.ingest
   :members:
```
