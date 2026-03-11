"""Lightweight async client for the memU Cloud REST API (v3)."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import httpx

from memu_mcp.auth import AuthError

logger = logging.getLogger("memu_mcp.client")

DEFAULT_BASE_URL = "https://api.memu.so"
DEFAULT_TIMEOUT = 30


class MemuCloudError(Exception):
    """Non-auth error returned by the memU Cloud API."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"memU API error (HTTP {status_code}): {detail}")


class MemuCloudClient:
    """Async wrapper around the memU Cloud REST API.

    All memory operations are delegated to the cloud; this client only
    needs an API key and (optionally) a custom base URL.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request and return the parsed JSON body.

        Raises ``AuthError`` on 401, ``MemuCloudError`` on other non-2xx.
        """
        try:
            resp = await self._client.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            msg = f"Failed to reach memU Cloud API: {exc}"
            raise MemuCloudError(0, msg) from exc

        if resp.status_code == 401:
            detail = "invalid or expired API key"
            with contextlib.suppress(Exception):
                detail = resp.json().get("error", detail)
            raise AuthError(f"Authentication failed: {detail}")  # noqa: TRY003

        if resp.status_code >= 400:
            detail = resp.text
            with contextlib.suppress(Exception):
                detail = resp.json().get("error", detail)
            raise MemuCloudError(resp.status_code, detail)

        if resp.status_code == 204:
            return {}

        return resp.json()

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def memorize(
        self,
        conversation: list[dict[str, str]],
        user_id: str,
        agent_id: str,
        *,
        user_name: str | None = None,
        agent_name: str | None = None,
        session_date: str | None = None,
        conversation_text: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v3/memory/memorize — start an async memorization task.

        Returns ``{"task_id": "..."}`` on success.
        """
        body: dict[str, Any] = {
            "conversation": conversation,
            "user_id": user_id,
            "agent_id": agent_id,
        }
        if user_name is not None:
            body["user_name"] = user_name
        if agent_name is not None:
            body["agent_name"] = agent_name
        if session_date is not None:
            body["session_date"] = session_date
        if conversation_text is not None:
            body["conversation_text"] = conversation_text

        return await self._request("POST", "/api/v3/memory/memorize", json=body)

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """GET /api/v3/memory/memorize/status/{task_id} — poll task status."""
        return await self._request("GET", f"/api/v3/memory/memorize/status/{task_id}")

    async def retrieve(
        self,
        query: str,
        user_id: str,
        agent_id: str,
    ) -> dict[str, Any]:
        """POST /api/v3/memory/retrieve — search memories."""
        body: dict[str, Any] = {
            "query": query,
            "user_id": user_id,
            "agent_id": agent_id,
        }
        return await self._request("POST", "/api/v3/memory/retrieve", json=body)

    async def list_categories(
        self,
        user_id: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v3/memory/categories — list memory categories."""
        body: dict[str, Any] = {"user_id": user_id}
        if agent_id is not None:
            body["agent_id"] = agent_id
        return await self._request("POST", "/api/v3/memory/categories", json=body)

    async def clear_memory(
        self,
        user_id: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v3/memory/clear — clear all memories."""
        body: dict[str, Any] = {"user_id": user_id}
        if agent_id is not None:
            body["agent_id"] = agent_id
        return await self._request("POST", "/api/v3/memory/clear", json=body)

    async def delete_memory(
        self,
        memory_id: str,
        user_id: str,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/memory/delete — delete a specific memory."""
        body: dict[str, Any] = {"memory_id": memory_id, "user_id": user_id}
        if agent_id is not None:
            body["agent_id"] = agent_id
        return await self._request("POST", "/api/v1/memory/delete", json=body)

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        await self._client.aclose()
