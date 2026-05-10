"""Load tools from the MCP server at startup and expose them to the agent."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_client = None
_tools: list = []


async def init_mcp_tools() -> list:
    """Call once at service startup inside the FastAPI lifespan."""
    global _client, _tools

    mcp_url = os.environ.get("MCP_URL", "http://127.0.0.1:8765/mcp")

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        _client = MultiServerMCPClient(
            {
                "main": {
                    "transport": "streamable_http",
                    "url": mcp_url,
                }
            }
        )
        # langchain-mcp-adapters ≥0.1.0: call get_tools() directly (no context manager)
        _tools = await _client.get_tools()
        logger.info("Loaded %d MCP tools from %s", len(_tools), mcp_url)
    except Exception as exc:
        logger.warning(
            "Could not connect to MCP server at %s: %s. Running without MCP tools.",
            mcp_url,
            exc,
        )
        _tools = []

    return _tools


async def close_mcp_client() -> None:
    # No teardown needed without context manager
    global _client
    _client = None


def get_mcp_tools() -> list:
    return list(_tools)
