"""Tests for the memU Cloud API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from memu_mcp.auth import AuthError
from memu_mcp.client import DEFAULT_BASE_URL, MemuCloudClient, MemuCloudError


@pytest.fixture()
def client():
    return MemuCloudClient(api_key="test-key")


@pytest.fixture()
def client_custom_url():
    return MemuCloudClient(api_key="test-key", base_url="https://custom.example.com")


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> httpx.Response:
    data = json_data or {}
    return httpx.Response(
        status_code=status_code,
        json=data,
        request=httpx.Request("POST", f"{DEFAULT_BASE_URL}/test"),
    )


# ---------------------------------------------------------------------------
# Auth / error handling
# ---------------------------------------------------------------------------


class TestRequestErrors:
    async def test_401_raises_auth_error(self, client):
        resp = _mock_response(401, {"error": "invalid_token"})
        with (
            patch.object(client._client, "request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(AuthError, match="invalid_token"),
        ):
            await client.retrieve(query="q", user_id="u1", agent_id="a1")

    async def test_400_raises_cloud_error(self, client):
        resp = _mock_response(400, {"error": "bad request"})
        with (
            patch.object(client._client, "request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(MemuCloudError, match="bad request"),
        ):
            await client.retrieve(query="q", user_id="u1", agent_id="a1")

    async def test_500_raises_cloud_error(self, client):
        resp = _mock_response(500, {"error": "internal"})
        with (
            patch.object(client._client, "request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(MemuCloudError) as exc_info,
        ):
            await client.retrieve(query="q", user_id="u1", agent_id="a1")
        assert exc_info.value.status_code == 500

    async def test_network_error_raises_cloud_error(self, client):
        with patch.object(
            client._client,
            "request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ), pytest.raises(MemuCloudError, match="Failed to reach memU Cloud API"):
            await client.retrieve(query="q", user_id="u1", agent_id="a1")


# ---------------------------------------------------------------------------
# memorize
# ---------------------------------------------------------------------------


class TestMemorize:
    async def test_memorize_sends_correct_request(self, client):
        resp = _mock_response(200, {"task_id": "task-123"})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.memorize(
                conversation=[
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                    {"role": "user", "content": "remember me"},
                ],
                user_id="u1",
                agent_id="a1",
            )

        assert result == {"task_id": "task-123"}
        mock_req.assert_awaited_once()
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1].endswith("/api/v3/memory/memorize")
        body = call_args[1]["json"]
        assert body["user_id"] == "u1"
        assert body["agent_id"] == "a1"
        assert len(body["conversation"]) == 3

    async def test_memorize_optional_fields(self, client):
        resp = _mock_response(200, {"task_id": "task-456"})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            await client.memorize(
                conversation=[
                    {"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                    {"role": "user", "content": "c"},
                ],
                user_id="u1",
                agent_id="a1",
                user_name="Alice",
                agent_name="Bot",
                session_date="2025-01-01",
            )

        body = mock_req.call_args[1]["json"]
        assert body["user_name"] == "Alice"
        assert body["agent_name"] == "Bot"
        assert body["session_date"] == "2025-01-01"
        assert "conversation_text" not in body


# ---------------------------------------------------------------------------
# get_task_status
# ---------------------------------------------------------------------------


class TestGetTaskStatus:
    async def test_get_task_status(self, client):
        resp = _mock_response(200, {"status": "completed", "task_id": "task-123"})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.get_task_status("task-123")

        assert result["status"] == "completed"
        call_args = mock_req.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1].endswith("/api/v3/memory/memorize/status/task-123")


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------


class TestRetrieve:
    async def test_retrieve_sends_correct_request(self, client):
        resp = _mock_response(200, {"items": [{"summary": "likes coffee"}]})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.retrieve(query="preferences", user_id="u1", agent_id="a1")

        assert result == {"items": [{"summary": "likes coffee"}]}
        body = mock_req.call_args[1]["json"]
        assert body == {"query": "preferences", "user_id": "u1", "agent_id": "a1"}


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


class TestListCategories:
    async def test_list_categories(self, client):
        resp = _mock_response(200, {"categories": ["profile", "preferences"]})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.list_categories(user_id="u1")

        assert result == {"categories": ["profile", "preferences"]}
        body = mock_req.call_args[1]["json"]
        assert body == {"user_id": "u1"}
        assert "agent_id" not in body

    async def test_list_categories_with_agent(self, client):
        resp = _mock_response(200, {"categories": []})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            await client.list_categories(user_id="u1", agent_id="a1")

        body = mock_req.call_args[1]["json"]
        assert body == {"user_id": "u1", "agent_id": "a1"}


# ---------------------------------------------------------------------------
# clear_memory
# ---------------------------------------------------------------------------


class TestClearMemory:
    async def test_clear_memory(self, client):
        resp = _mock_response(200, {"cleared": True})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.clear_memory(user_id="u1")

        assert result == {"cleared": True}
        body = mock_req.call_args[1]["json"]
        assert body == {"user_id": "u1"}


# ---------------------------------------------------------------------------
# delete_memory
# ---------------------------------------------------------------------------


class TestDeleteMemory:
    async def test_delete_memory(self, client):
        resp = _mock_response(200, {"deleted": True})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            result = await client.delete_memory(memory_id="m1", user_id="u1")

        assert result == {"deleted": True}
        body = mock_req.call_args[1]["json"]
        assert body == {"memory_id": "m1", "user_id": "u1"}

    async def test_delete_memory_with_agent(self, client):
        resp = _mock_response(200, {"deleted": True})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client._client, "request", mock_req):
            await client.delete_memory(memory_id="m1", user_id="u1", agent_id="a1")

        body = mock_req.call_args[1]["json"]
        assert body == {"memory_id": "m1", "user_id": "u1", "agent_id": "a1"}


# ---------------------------------------------------------------------------
# Custom base URL
# ---------------------------------------------------------------------------


class TestCustomBaseUrl:
    async def test_uses_custom_url(self, client_custom_url):
        resp = _mock_response(200, {"categories": []})
        mock_req = AsyncMock(return_value=resp)

        with patch.object(client_custom_url._client, "request", mock_req):
            await client_custom_url.list_categories(user_id="u1")

        url = mock_req.call_args[0][1]
        assert url.startswith("https://custom.example.com/")


# ---------------------------------------------------------------------------
# Bearer token header
# ---------------------------------------------------------------------------


class TestAuthHeader:
    async def test_bearer_token_in_default_headers(self, client):
        assert client._client.headers["authorization"] == "Bearer test-key"
