---
description: "Reference for InstallomatorClient: the standalone fetcher for Installomator label scripts."
---

# Installomator

:::{warning}
`InstallomatorClient` is deprecated and will be removed in a future release. For label
and match data, prefer {class}`~patcher.core.patcher_client.PatcherClient` /
{class}`~patcher.clients.patcher_api.PatcherAPIClient` (set `PATCHER_API_URL` for
self-hosted catalogs). Constructing the client emits a `DeprecationWarning`.
:::

:::{seealso}
{doc}`/project/sources` for what each catalog source contributes.
:::

```{eval-rst}
.. autoclass:: patcher.clients.installomator.InstallomatorClient
   :members:
```

`InstallomatorClient` covers label discovery and fetch:
{meth}`~patcher.clients.installomator.InstallomatorClient.list_available_labels`,
{meth}`~patcher.clients.installomator.InstallomatorClient.get_label`,
{meth}`~patcher.clients.installomator.InstallomatorClient.get_labels`.
The match algorithm itself lives at module level in
{mod}`patcher.core.matching` so other backends can exercise it without
instantiating the client.

:::{note}
The shell-pipeline resolver that historically lived alongside `InstallomatorClient` (`resolve`, `_exec_*`, `is_shell_expression`, `looks_like_clean_http_url`, `Resolved`/`Unresolvable`/`InvalidOutput`) moved to `patcher_api.installomator.resolver` as part of the Patcher API workspace. Resolution is an ingest concern; the `patcher` package consumes resolved values via the API rather than running pipelines itself.
:::
