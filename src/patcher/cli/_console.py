# Shared Rich consoles. Import these instead of constructing new ones so width/theme stays consistent.
"""
Shared Rich console singletons and palette constants for the Patcher CLI.

Every CLI module that wants to emit Rich-rendered output (panels, spinners,
tracebacks, styled text) should import :data:`console` and :data:`err_console`
from here. Constructing fresh ``Console()`` objects per callsite leads to
inconsistent width detection, mixed themes, and double-rendered output when
two consoles share the same terminal.

The palette constants mirror the fastmcp/cyclopts convention so any future
migration of ``click.echo`` callsites can reference a single source of truth.
"""

from rich.console import Console

console = Console()
err_console = Console(stderr=True)

INFO_STYLE = "cyan"
WARNING_STYLE = "yellow"
ERROR_STYLE = "red"
SUCCESS_STYLE = "green"
DIM_STYLE = "dim"
