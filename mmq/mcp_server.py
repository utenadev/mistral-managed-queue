# mmq/mcp_server.py
"""MCP server setup and tool registration."""

from __future__ import annotations

import os
import logging
from typing import Optional

from mcp.server.fastmcp import Context, FastMCP

# MCP server instance (always created so ``mmq --mcp`` works out of the box)
mcp = FastMCP("mistral-managed-queue")

# Optional HTTP run mode (``mmq mcp run``); override via env var
_MCP_ENABLED = os.environ.get("MMQ_ENABLE_MCP", "").lower() in ("1", "true", "yes", "on")

logger = logging.getLogger("mistral-managed-queue")

def start_mcp_server_stdio() -> None:
    """Start the MCP server on stdio (used by ``mmq --mcp``)."""
    mcp.run(transport="stdio")

def start_mcp_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server over HTTP (used by ``mmq mcp run``)."""
    logger.info("Starting MCP server: http://%s:%s", host, port)
    mcp.run(host=host, port=port)

# ---- MCP tool registration ----
from .db import read_queue_status
from .core import (
    execute_mistral_queue_async,
    MistralRequest,
)

@mcp.tool()
async def ask_mistral(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """Ask Mistral via MCP. Queues the request and waits for the result."""
    return await execute_mistral_queue_async(
        MistralRequest(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
        )
    )

@mcp.tool()
def get_queue_status() -> dict:
    """Return the current queue status."""
    return read_queue_status()
