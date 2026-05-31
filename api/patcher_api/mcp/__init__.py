"""
MCP server for the Patcher catalog.

Importing this package eagerly registers every tool, resource, and prompt on
the ``mcp`` instance so any consumer (the FastAPI mount in ``main.py``, tests,
the dev inspector) gets a fully populated server. Registration happens at
import time via the ``@mcp.tool`` / ``@mcp.resource`` / ``@mcp.prompt``
decorators, so each module is imported here for its side effects.
"""

from patcher_api.mcp import prompts, resources, tools  # noqa: F401  -- decorator side effects
from patcher_api.mcp.server import mcp, mcp_app

__all__ = ["mcp", "mcp_app"]
