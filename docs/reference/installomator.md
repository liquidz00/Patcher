# Installomator

:::{seealso}
{doc}`/usage/installomator` for the matching algorithm walkthrough.
:::

```{autoclass} patcher.clients.installomator.InstallomatorClient
:members:
```

:::{note}
The shell-pipeline resolver that historically lived alongside `InstallomatorClient` (`resolve`, `_exec_*`, `is_shell_expression`, `looks_like_clean_http_url`, `Resolved`/`Unresolvable`/`InvalidOutput`) moved to `patcher_api.installomator_resolver` as part of the Patcher API workspace. Resolution is an ingest concern; the `patcher` package consumes resolved values via the API rather than running pipelines itself.
:::
