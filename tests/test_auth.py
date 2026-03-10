"""Tests for the memU cloud token validation module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from memu_mcp.auth import MEMU_API_BASE_URL, _AUTH_PROBE_PATH, AuthError, TokenValidator

_PROBE_URL = f"{MEMU_API_BASE_URL}{_AUTH_PROBE_PATH}"


@pytest.fixture()
def validator():
    return TokenValidator(cache_ttl=60)


@pytest.fixture()
def validator_custom_url():
    return TokenValidator(api_base_url="https://custom.example.com", cache_ttl=60)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    data = json_data or {}
    return httpx.Response(status_code=status_code, json=data, request=httpx.Request("POST", _PROBE_URL))


class TestValidateSuccess:
    async def test_returns_authenticated(self, validator):
        mock_resp = _mock_response(200, {"categories": []})

        with patch.object(validator._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            result = await validator.validate("valid-token")

        assert result == {"authenticated": True}

    async def test_sends_bearer_header_and_probe_params(self, validator):
        mock_resp = _mock_response(200, {"categories": []})
        mock_post = AsyncMock(return_value=mock_resp)

        with patch.object(validator._client, "post", mock_post):
            await validator.validate("my-token")

        mock_post.assert_awaited_once_with(
            _PROBE_URL,
            json={"user_id": "_auth_probe"},
            headers={"Authorization": "Bearer my-token"},
        )


class TestValidateInvalidToken:
    async def test_raises_auth_error_on_401(self, validator):
        mock_resp = _mock_response(401, {"error": "invalid_token"})

        with patch.object(validator._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(AuthError, match="invalid_token"):
                await validator.validate("bad-token")

    async def test_raises_auth_error_on_unexpected_status(self, validator):
        mock_resp = _mock_response(500, {"error": "internal"})

        with patch.object(validator._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(AuthError, match="Unexpected auth response"):
                await validator.validate("some-token")

    async def test_raises_auth_error_on_network_failure(self, validator):
        with patch.object(
            validator._client, "post", new_callable=AsyncMock, side_effect=httpx.ConnectError("connection refused")
        ):
            with pytest.raises(AuthError, match="Failed to reach memU auth service"):
                await validator.validate("some-token")


class TestCache:
    async def test_cache_hit_avoids_second_call(self, validator):
        mock_resp = _mock_response(200, {"categories": []})
        mock_post = AsyncMock(return_value=mock_resp)

        with patch.object(validator._client, "post", mock_post):
            result1 = await validator.validate("token-a")
            result2 = await validator.validate("token-a")

        assert result1 == result2 == {"authenticated": True}
        mock_post.assert_awaited_once()

    async def test_different_tokens_not_cached_together(self, validator):
        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_response(200, {"categories": []})

        with patch.object(validator._client, "post", new_callable=AsyncMock, side_effect=_side_effect):
            result_a = await validator.validate("token-a")
            result_b = await validator.validate("token-b")

        assert result_a == result_b == {"authenticated": True}
        assert call_count == 2

    async def test_cache_expiry(self, validator):
        mock_resp = _mock_response(200, {"categories": []})
        mock_post = AsyncMock(return_value=mock_resp)

        with patch.object(validator._client, "post", mock_post):
            await validator.validate("token-a")

            for key in validator._cache:
                ts, info = validator._cache[key]
                validator._cache[key] = (ts - validator._cache_ttl - 1, info)

            await validator.validate("token-a")

        assert mock_post.await_count == 2


class TestCustomBaseUrl:
    async def test_uses_custom_url(self, validator_custom_url):
        custom_probe_url = f"https://custom.example.com{_AUTH_PROBE_PATH}"
        mock_resp = httpx.Response(
            200,
            json={"categories": []},
            request=httpx.Request("POST", custom_probe_url),
        )
        mock_post = AsyncMock(return_value=mock_resp)

        with patch.object(validator_custom_url._client, "post", mock_post):
            await validator_custom_url.validate("token")

        mock_post.assert_awaited_once_with(
            custom_probe_url,
            json={"user_id": "_auth_probe"},
            headers={"Authorization": "Bearer token"},
        )
