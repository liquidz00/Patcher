---
description: "Reference for patcher.core.analyze: the TitleFilter and TrendAnalysis classes that filter, rank, and trend patch data."
---

(analyzer)=

# Analyze

```{versionchanged} 3.0
`FilterCriteria` and `TrendCriteria` enums, plus the `Analyzer` wrapper and `BaseEnum.from_cli` helper, were replaced by {class}`~patcher.core.analyze.TitleFilter` and {class}`~patcher.core.analyze.TrendAnalysis`. Each former enum value is now a method on the respective class with its own signature.
```

```{eval-rst}
.. py:module:: patcher.core.analyze

.. autoclass:: TitleFilter
   :members:
   :exclude-members: criteria, apply

   .. automethod:: criteria
   .. automethod:: apply

.. autoclass:: TrendAnalysis
   :members:
   :exclude-members: criteria, apply, from_cache

   .. automethod:: from_cache
   .. automethod:: criteria
   .. automethod:: apply

.. autoclass:: Diff
   :members:
   :exclude-members: compute, from_cache, live_vs_cache

   .. automethod:: compute
   .. automethod:: from_cache
   .. automethod:: live_vs_cache

.. autoclass:: DiffResult
   :members:

.. autoclass:: TitleChange
   :members:

.. autofunction:: sort_titles

.. autofunction:: omit_recent

.. autofunction:: append_ios_status

.. py:module:: patcher.core.matching
   :no-index:

.. autofunction:: match_titles
```
