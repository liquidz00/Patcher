---
description: "Reference for PatcherSettings: Patcher's on-disk configuration model (UI styling, matching toggles, integrations, interpreter path)."
---

# Settings Model

`PatcherSettings` is the single home for Patcher's on-disk configuration: UI
branding (`UIDefaults`), the matching toggle, `Integrations`, ignored titles,
and the recorded interpreter path. It reads and writes
`com.liquidzoo.patcher.plist` via `load()` / `save()`, folding older plist
formats forward on read.

```{eval-rst}
.. automodule:: patcher.core.models.settings
   :members:
   :exclude-members: model_computed_fields, model_config, model_fields
```
