"""
MCP server for the Patcher catalog.

Importing this package eagerly registers every tool defined in :mod:`tools`
on the ``mcp`` instance so any consumer (the FastAPI mount in ``main.py``,
tests, the dev inspector) gets a fully populated server. Tool registration
happens at import time via the ``@mcp.tool`` decorator.
"""

from patcher_api.mcp import tools  # noqa: F401  -- import for decorator side effects
from patcher_api.mcp.server import mcp, mcp_app

__all__ = ["mcp", "mcp_app"]
