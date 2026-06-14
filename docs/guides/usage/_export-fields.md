A `PatchTitle` carries a few fields that exist purely as internal metadata. For example, `title_id` and `name_id` are Jamf join keys, and `install_label` / `homebrew_cask` are raw matcher output. Whether those reach an export depends on the format, because the formats serve two different audiences.

::::{markers}

:::{marker} Rendered reports (PDF, Excel, HTML)
:icon: octicon:file-badge-16

For a human reading a patch report. The {class}`~patcher.core.exporter.Exporter` drops configured columns before rendering, so the join keys and raw matcher fields never show up as columns.
:::

:::{marker} JSON
:icon: mdi:code-json

Machine-to-machine transport. It is serialized straight from the models via {func}`~patcher.core.serialization.titles_to_dict`, so it keeps **every** field. A downstream consumer building a dashboard, alerting pipeline, or other similar type of automation benefits from these identifiers.
:::
::::

```{seealso}
For information about what is ignored and when, see {ref}`catalog constants <catalog-constants>` in the policy module reference docs.
```
