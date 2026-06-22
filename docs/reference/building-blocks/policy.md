---
description: "Reference for the catalog filter/seed constants (patcher.policy)."
---

# Policy

The policy module's purpose is to act as the catalog rules that are deliberately hardcoded rather than user-configurable. Each constant is owned by a different layer (ingest, matching, stitch, export) and is independent of the others. They live in one module so the decisions are reviewable in a single place instead of being scattered next to the code that happens to read them.

(catalog-constants)=
## Catalog constants

```{eval-rst}
.. autodata:: patcher.policy.INGEST_EXCLUDED_TEAM_IDS
```

```{eval-rst}
.. autodata:: patcher.policy.IGNORED_TITLES
```

```{eval-rst}
.. autodata:: patcher.policy.CURATED_BUNDLE_IDS
```

```{eval-rst}
.. autodata:: patcher.policy.IGNORED_EXPORT_COLUMNS
```
