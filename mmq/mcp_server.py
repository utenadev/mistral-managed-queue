# mmq/mcp_server.py
"""MCP server setup and tool registration (lazy init — FastMCP imported on demand)."""

from __future__ import annotations

import os
import logging
from typing import Optional

# _MCP_ENABLED is a lightweight env-var check; no FastMCP import needed.
_MCP_ENABLED = os.environ.get("MMQ_ENABLE_MCP", "").lower() in ("1", "true", "yes", "on")

logger = logging.getLogger("mistral-managed-queue")

_mcp_instance = None


def _get_mcp():
    """Get or create the singleton FastMCP instance (lazy init)."""
    global _mcp_instance
    if _mcp_instance is None:
        from mcp.server.fastmcp import FastMCP

        _mcp_instance = FastMCP("mistral-managed-queue")

        # Register tools inside lazy init so FastMCP is only loaded when needed.
        from .db import read_queue_status
        from .core import execute_mistral_queue_async, MistralRequest

        @_mcp_instance.tool()
        async def ask_mistral(
            prompt: str,
            model: Optional[str] = None,
            system_prompt: Optional[str] = None
        ) -> str:
            """Ask Mistral via MCP. Queues the request and waits for the result."""
            return await execute_mistral_queue_async(
                MistralRequest(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                )
            )

        @_mcp_instance.tool()
        def get_queue_status() -> dict:
            """Return the current queue status."""
            return read_queue_status()

    return _mcp_instance


def start_mcp_server_stdio() -> None:
    """Start the MCP server on stdio (used by ``mmq --mcp``)."""
    _get_mcp().run(transport="stdio")


def start_mcp_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server over HTTP (used by ``mmq mcp run``)."""
    logger.info("Starting MCP server: http://%s:%s", host, port)
    _get_mcp().run(host=host, port=port)