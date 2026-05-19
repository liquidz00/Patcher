# Reference

Auto-generated API reference, grouped by source layout. Sections mirror the package's top-level directories (`clients/`, `core/`, `cli/`, plus the model subpackage) so navigating from "I'm reading the source" to "where are the docs for this" is one-to-one.

```{toctree}
:caption: Command-line
:maxdepth: 2

cli
```

Every `patcherctl` flag, subcommand, exit code, and environment variable in one place.

```{toctree}
:caption: Top-Level
:maxdepth: 3

patcher_client
```

Library entry point. The orchestrator that composes the per-service clients, the data layer, and the matching pipeline.

```{toctree}
:caption: Clients
:maxdepth: 3

http_client
jamf_client
patcher_api_client
installomator
token_manager
```

`src/patcher/clients/`. HTTPClient is the shared httpx-with-truststore base; JamfClient and PatcherAPIClient are the per-service wrappers. InstallomatorClient is a standalone label fetcher; TokenManager handles Jamf OAuth bookkeeping.

```{toctree}
:caption: Core
:maxdepth: 3

analyze
config_manager
data_manager
exceptions
fonts
logger
pdf_report
plist_manager
```

`src/patcher/core/`. Analysis primitives, configuration loading, on-disk patch-data cache, exception hierarchy, logging, PDF report writer, and macOS plist read/write.

```{toctree}
:caption: CLI
:maxdepth: 3

animation
report
setup
terminal_logger
ui_manager
```

`src/patcher/cli/`. Setup wizard, report orchestration, terminal animation, and the click-styled logging adapter. These power `patcherctl` and aren't part of the library's stable surface.

```{toctree}
:caption: Models
:maxdepth: 2

fragment
jamf_models
label
patch
token
ui
```

`src/patcher/core/models/`. Pydantic data shapes shared across the package. `PatchTitle` and `PatchDevice` are the return shapes for `PatcherClient.fetch_patches` and the per-device report flows.
