"""Tests for the MCP server module (Cloud API version)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

import memu_mcp.server as mcp_mod
from memu_mcp.client import MemuCloudClient
from memu_mcp.server import (
    _get_client,
    clear_memory,
    delete_memory,
    get_task_status,
    init_mcp_server,
    list_categories,
    memorize,
    retrieve,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client():
    """Create a mock MemuCloudClient with all methods as AsyncMocks."""
    client = AsyncMock(spec=MemuCloudClient)
    client.memorize = AsyncMock(return_value={"task_id": "task-123"})
    client.get_task_status = AsyncMock(return_value={"status": "completed", "task_id": "task-123"})
    client.retrieve = AsyncMock(return_value={"items": [{"summary": "likes coffee"}]})
    client.list_categories = AsyncMock(return_value={"categories": ["profile"]})
    client.clear_memory = AsyncMock(return_value={"cleared": True})
    client.delete_memory = AsyncMock(return_value={"deleted": True})
    init_mcp_server(client)
    yield client
    mcp_mod._client = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_raises_when_not_initialized(self):
        mcp_mod._client = None
        with pytest.raises(RuntimeError, match="MemuCloudClient not initialized"):
            _get_client()


# ---------------------------------------------------------------------------
# memorize
# ---------------------------------------------------------------------------


class TestMemorizeTool:
    async def test_memorize_delegates_to_client(self, mock_client):
        conversation = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "remember me"},
        ]
        result_json = await memorize(
            conversation=conversation,
            user_id="u1",
            agent_id="a1",
        )
        result = json.loads(result_json)
        assert result == {"task_id": "task-123"}

        mock_client.memorize.assert_awaited_once_with(
            conversation=conversation,
            user_id="u1",
            agent_id="a1",
            user_name=None,
            agent_name=None,
            session_date=None,
            conversation_text=None,
        )

    async def test_memorize_with_optional_fields(self, mock_client):
        conversation = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        await memorize(
            conversation=conversation,
            user_id="u1",
            agent_id="a1",
            user_name="Alice",
            agent_name="Bot",
            session_date="2025-01-01",
        )

        mock_client.memorize.assert_awaited_once_with(
            conversation=conversation,
            user_id="u1",
            agent_id="a1",
            user_name="Alice",
            agent_name="Bot",
            session_date="2025-01-01",
            conversation_text=None,
        )


# ---------------------------------------------------------------------------
# get_task_status
# ---------------------------------------------------------------------------


class TestGetTaskStatusTool:
    async def test_get_task_status(self, mock_client):
        result_json = await get_task_status(task_id="task-123")
        result = json.loads(result_json)
        assert result["status"] == "completed"
        mock_client.get_task_status.assert_awaited_once_with("task-123")


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


class TestRetrieveTool:
    async def test_retrieve_delegates_to_client(self, mock_client):
        result_json = await retrieve(query="preferences", user_id="u1", agent_id="a1")
        result = json.loads(result_json)
        assert result == {"items": [{"summary": "likes coffee"}]}

        mock_client.retrieve.assert_awaited_once_with(
            query="preferences",
            user_id="u1",
            agent_id="a1",
        )


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


class TestListCategoriesTool:
    async def test_list_categories(self, mock_client):
        result_json = await list_categories(user_id="u1")
        result = json.loads(result_json)
        assert result == {"categories": ["profile"]}

        mock_client.list_categories.assert_awaited_once_with(
            user_id="u1",
            agent_id=None,
        )

    async def test_list_categories_with_agent(self, mock_client):
        await list_categories(user_id="u1", agent_id="a1")
        mock_client.list_categories.assert_awaited_once_with(
            user_id="u1",
            agent_id="a1",
        )


# ---------------------------------------------------------------------------
# delete_memory
# ---------------------------------------------------------------------------


class TestDeleteMemoryTool:
    async def test_delete_memory(self, mock_client):
        result_json = await delete_memory(memory_id="m1", user_id="u1")
        result = json.loads(result_json)
        assert result == {"deleted": True}

        mock_client.delete_memory.assert_awaited_once_with(
            memory_id="m1",
            user_id="u1",
            agent_id=None,
        )


# ---------------------------------------------------------------------------
# clear_memory
# ---------------------------------------------------------------------------


class TestClearMemoryTool:
    async def test_clear_memory(self, mock_client):
        result_json = await clear_memory(user_id="u1")
        result = json.loads(result_json)
        assert result == {"cleared": True}

        mock_client.clear_memory.assert_awaited_once_with(
            user_id="u1",
            agent_id=None,
        )

    async def test_clear_memory_with_agent(self, mock_client):
        await clear_memory(user_id="u1", agent_id="a1")
        mock_client.clear_memory.assert_awaited_once_with(
            user_id="u1",
            agent_id="a1",
        )
