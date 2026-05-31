---
description: "Reference for patcher_api.drift — detects cross-source version disagreement on tracked apps."
---

# drift

Per-app comparison of versions reported by participating sources (currently Installomator and Homebrew Cask). Surfaces apps where sources disagree on what "latest" means, the case where one source has silently fallen behind. Powers the `/apps/drift` endpoint and the `list_drift` MCP tool.

```{eval-rst}
.. autofunction:: patcher_api.drift.extract_versions

.. autofunction:: patcher_api.drift.detect_drift
```
