---
description: "Reference for patcher.core.serialization: the conversions between PatchTitle objects and their DataFrame and dict representations."
---

# Serialization

The single home for converting `PatchTitle` objects to and from their DataFrame and dict forms. {class}`~patcher.core.data_manager.DataManager` (cache round-trip), {class}`~patcher.core.exporter.Exporter` (JSON output), and the trend-analysis diff path all share these functions instead of each re-implementing `model_dump`.

```{eval-rst}
.. autofunction:: patcher.core.serialization.titles_to_df

.. autofunction:: patcher.core.serialization.df_to_titles

.. autofunction:: patcher.core.serialization.titles_to_dict
```
