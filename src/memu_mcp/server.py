"""MCP (Model Context Protocol) server for memU Cloud API."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from typing import Any

from memu_mcp.client import MemuCloudClient

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    msg = "Please install 'mcp' package: pip install mcp"
    raise ImportError(msg) from e

logger = logging.getLogger("memu_mcp.server")

mcp_server = FastMCP("memu")

_client: MemuCloudClient | None = None


def init_mcp_server(client: MemuCloudClient) -> FastMCP:
    """Bind a MemuCloudClient instance to the MCP server."""
    global _client
    _client = client
    return mcp_server


def _get_client() -> MemuCloudClient:
    if _client is None:
        msg = "MemuCloudClient not initialized. Call init_mcp_server() or use the memu-mcp CLI."
        raise RuntimeError(msg)
    return _client


def _json(result: Any) -> str:
    return json.dumps(result, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp_server.tool()
async def memorize(
    conversation: list[dict[str, str]],
    user_id: str,
    agent_id: str,
    user_name: str | None = None,
    agent_name: str | None = None,
    session_date: str | None = None,
    conversation_text: str | None = None,
) -> str:
    """Save a conversation to memU cloud memory (async). Returns a task_id for status polling.

    The conversation must contain at least 3 messages. Each message is a dict
    with "role" (e.g. "user", "assistant") and "content" keys.

    Args:
        conversation: List of message dicts, each with "role" and "content" keys. Minimum 3 messages.
        user_id: User identifier.
        agent_id: Agent identifier.
        user_name: Optional human-readable user name.
        agent_name: Optional human-readable agent name.
        session_date: Optional date string for the conversation session.
        conversation_text: Optional pre-formatted conversation text.
    """
    client = _get_client()
    result = await client.memorize(
        conversation=conversation,
        user_id=user_id,
        agent_id=agent_id,
        user_name=user_name,
        agent_name=agent_name,
        session_date=session_date,
        conversation_text=conversation_text,
    )
    return _json(result)


@mcp_server.tool()
async def get_task_status(task_id: str) -> str:
    """Check the status of an async memorization task.

    Args:
        task_id: The task ID returned by the memorize tool.
    """
    client = _get_client()
    result = await client.get_task_status(task_id)
    return _json(result)


@mcp_server.tool()
async def retrieve(
    query: str,
    user_id: str,
    agent_id: str,
) -> str:
    """Search for relevant memories based on a query.

    Args:
        query: The search query to find relevant memories.
        user_id: User identifier.
        agent_id: Agent identifier.
    """
    client = _get_client()
    result = await client.retrieve(
        query=query,
        user_id=user_id,
        agent_id=agent_id,
    )
    return _json(result)


@mcp_server.tool()
async def list_categories(
    user_id: str,
    agent_id: str | None = None,
) -> str:
    """List all memory categories for a user.

    Args:
        user_id: User identifier.
        agent_id: Optional agent identifier.
    """
    client = _get_client()
    result = await client.list_categories(
        user_id=user_id,
        agent_id=agent_id,
    )
    return _json(result)


@mcp_server.tool()
async def delete_memory(
    memory_id: str,
    user_id: str,
    agent_id: str | None = None,
) -> str:
    """Delete a specific memory item by ID.

    Args:
        memory_id: The ID of the memory item to delete.
        user_id: User identifier.
        agent_id: Optional agent identifier.
    """
    client = _get_client()
    result = await client.delete_memory(
        memory_id=memory_id,
        user_id=user_id,
        agent_id=agent_id,
    )
    return _json(result)


@mcp_server.tool()
async def clear_memory(
    user_id: str,
    agent_id: str | None = None,
) -> str:
    """Clear all memories for a user. This action is irreversible.

    Args:
        user_id: User identifier.
        agent_id: Optional agent identifier.
    """
    client = _get_client()
    result = await client.clear_memory(
        user_id=user_id,
        agent_id=agent_id,
    )
    return _json(result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _resolve(cli_value: str | None, env_key: str, default: str | None = None) -> str | None:
    """Resolve a config value: CLI arg > env var > default."""
    if cli_value is not None:
        return cli_value
    return os.environ.get(env_key, default)


def main() -> None:
    """CLI entry point for the memU MCP server."""
    import argparse

    with contextlib.suppress(ImportError):
        from dotenv import load_dotenv

        load_dotenv()

    parser = argparse.ArgumentParser(
        description="memU MCP Server - memU Cloud API as MCP tools",
    )
    parser.add_argument("--memu-api-key", default=None, help="memU API key (env: MEMU_API_KEY)")
    parser.add_argument("--api-base-url", default=None, help="memU API base URL (env: MEMU_API_BASE_URL)")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="MCP transport (default: stdio)",
    )

    args = parser.parse_args()

    memu_api_key = _resolve(args.memu_api_key, "MEMU_API_KEY")
    if not memu_api_key:
        parser.error("memU API key is required. Set --memu-api-key or MEMU_API_KEY environment variable.")

    api_base_url = _resolve(args.api_base_url, "MEMU_API_BASE_URL") or "https://api.memu.so"

    client = MemuCloudClient(api_key=memu_api_key, base_url=api_base_url)
    init_mcp_server(client)

    logger.info("Starting memU MCP server (transport=%s, base_url=%s)", args.transport, api_base_url)
    mcp_server.run(transport=args.transport)
