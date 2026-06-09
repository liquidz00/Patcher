---
description: "Reference for the Patcher CLI's terminal output layer: console singletons, the status spinner, renderers, and the click-backed log handler."
---

# Console / Output

The CLI's terminal-output layer: the shared Rich console singletons and
palette, the debug-aware status spinner, the table / diff / drift renderers,
the error panel, and the logging that routes through the console (the terminal
handler and excepthook). Library callers who never import `patcher.cli` get
file-only logging and pay for none of this.

```{eval-rst}
.. automodule:: patcher.cli._console
   :members:
```
