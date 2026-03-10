"""memU cloud token validation with TTL cache."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("memu_mcp.auth")

MEMU_API_BASE_URL = "https://api.memu.so"
_AUTH_PROBE_PATH = "/api/v3/memory/categories"


class AuthError(Exception):
    """Raised when token validation fails."""


class TokenValidator:
    """Validates memU API tokens against the cloud endpoint.

    Sends a lightweight ``POST /api/v3/memory/categories`` request to
    verify the bearer token.  Maintains an in-memory TTL cache so
    repeated tool calls within ``cache_ttl`` seconds only require a
    single HTTP round-trip.
    """

    def __init__(self, api_base_url: str = MEMU_API_BASE_URL, cache_ttl: int = 300) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._client = httpx.AsyncClient(timeout=10)

    @property
    def _auth_probe_url(self) -> str:
        return f"{self._api_base_url}{_AUTH_PROBE_PATH}"

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate *token* and return cached auth info on success.

        Raises ``AuthError`` for invalid / expired tokens or network failures.
        """
        cached = self._cache.get(token)
        if cached is not None:
            ts, info = cached
            if time.monotonic() - ts < self._cache_ttl:
                return info
            del self._cache[token]

        try:
            resp = await self._client.post(
                self._auth_probe_url,
                json={"user_id": "_auth_probe"},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            msg = f"Failed to reach memU auth service: {exc}"
            raise AuthError(msg) from exc

        if resp.status_code == 401:
            detail = resp.json().get("error", "invalid_token")
            msg = f"Authentication failed: {detail}"
            raise AuthError(msg)

        if resp.status_code != 200:
            msg = f"Unexpected auth response (HTTP {resp.status_code})"
            raise AuthError(msg)

        info: dict[str, Any] = {"authenticated": True}
        self._cache[token] = (time.monotonic(), info)
        logger.debug("Token validated successfully")
        return info

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        await self._client.aclose()
