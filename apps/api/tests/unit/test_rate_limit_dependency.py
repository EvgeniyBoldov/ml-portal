from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps


class _FakeRedis:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, _key: str, _ttl: int) -> bool:
        return True


def _build_request(*, user_id: str | None = None, ip: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chats/test/messages",
        "headers": [],
        "client": (ip, 12345),
    }
    request = Request(scope)
    request.state.user = SimpleNamespace(id=user_id) if user_id else None
    return request


@pytest.mark.asyncio
async def test_rate_limit_dependency_blocks_after_rpm(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(deps, "get_redis", lambda: fake_redis)

    limiter = deps.rate_limit_dependency(key_prefix="test", rpm=2, rph=100)
    request = _build_request(user_id="u1")

    await limiter(request)
    await limiter(request)
    with pytest.raises(HTTPException) as exc:
        await limiter(request)

    assert exc.value.status_code == 429
    assert "Retry-After" in (exc.value.headers or {})


@pytest.mark.asyncio
async def test_rate_limit_dependency_fails_open_on_redis_error(monkeypatch):
    class _BrokenRedis:
        async def incr(self, _key: str) -> int:
            raise RuntimeError("redis down")

    monkeypatch.setattr(deps, "get_redis", lambda: _BrokenRedis())

    limiter = deps.rate_limit_dependency(key_prefix="test", rpm=1, rph=1)
    request = _build_request(ip="10.0.0.1")

    # Should not raise when redis is unavailable (fail-open).
    await limiter(request)

