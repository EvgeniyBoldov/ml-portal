"""
Contract tests for canonical IdempotencyManager.

Validates:
- Configurable prefix and TTL
- get_cached_result / cache_result round-trip
- delete method
- Graceful handling of Redis failures
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from app.core.idempotency import IdempotencyManager


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.delete = AsyncMock(return_value=1)
    return r


class TestIdempotencyManagerConfig:
    """Prefix and TTL must be configurable."""

    def test_default_prefix(self, mock_redis):
        mgr = IdempotencyManager(mock_redis)
        assert mgr.prefix == "chat:message:"
        assert mgr.ttl_seconds == 86400

    def test_custom_prefix(self, mock_redis):
        mgr = IdempotencyManager(mock_redis, prefix="rag:ingest:", ttl_seconds=3600)
        assert mgr.prefix == "rag:ingest:"
        assert mgr.ttl_seconds == 3600

    def test_make_key(self, mock_redis):
        mgr = IdempotencyManager(mock_redis, prefix="test:")
        assert mgr._make_key("abc") == "test:abc"


class TestGetCachedResult:
    """get_cached_result should parse JSON from Redis."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_cached(self, mock_redis):
        mgr = IdempotencyManager(mock_redis)
        result = await mgr.get_cached_result("key-1")
        assert result is None
        mock_redis.get.assert_awaited_once_with("chat:message:key-1")

    @pytest.mark.asyncio
    async def test_returns_cached_data(self, mock_redis):
        cached = {"user_message_id": "u-1", "assistant_message_id": "a-1"}
        mock_redis.get.return_value = json.dumps(cached).encode()
        mgr = IdempotencyManager(mock_redis)
        result = await mgr.get_cached_result("key-2")
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_failure(self, mock_redis):
        mock_redis.get.side_effect = ConnectionError("Redis down")
        mgr = IdempotencyManager(mock_redis)
        result = await mgr.get_cached_result("key-3")
        assert result is None


class TestCacheResult:
    """cache_result should store JSON in Redis with TTL."""

    @pytest.mark.asyncio
    async def test_stores_data(self, mock_redis):
        mgr = IdempotencyManager(mock_redis, prefix="p:", ttl_seconds=120)
        data = {"msg": "hello"}
        await mgr.cache_result("k1", data)
        mock_redis.setex.assert_awaited_once_with(
            "p:k1",
            120,
            json.dumps(data),
        )

    @pytest.mark.asyncio
    async def test_handles_redis_failure_gracefully(self, mock_redis):
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        mgr = IdempotencyManager(mock_redis)
        # Should not raise
        await mgr.cache_result("k2", {"data": 1})


class TestDelete:
    """delete should remove key and return True/False."""

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, mock_redis):
        mock_redis.delete.return_value = 1
        mgr = IdempotencyManager(mock_redis, prefix="d:")
        result = await mgr.delete("existing")
        assert result is True
        mock_redis.delete.assert_awaited_once_with("d:existing")

    @pytest.mark.asyncio
    async def test_delete_missing_key(self, mock_redis):
        mock_redis.delete.return_value = 0
        mgr = IdempotencyManager(mock_redis, prefix="d:")
        result = await mgr.delete("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_handles_failure(self, mock_redis):
        mock_redis.delete.side_effect = ConnectionError("Redis down")
        mgr = IdempotencyManager(mock_redis)
        result = await mgr.delete("fail")
        assert result is False
