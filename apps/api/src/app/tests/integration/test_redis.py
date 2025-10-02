"""
Интеграционные тесты для Redis.
Использует реальный Redis для проверки кеширования, сессий и pub/sub.
"""
import pytest
import asyncio
import json
import uuid
from datetime import datetime, timedelta

from app.core.cache import CacheManager
from app.core.session import SessionManager


@pytest.mark.integration
class TestRedisIntegration:
    """Интеграционные тесты для Redis."""

    @pytest.mark.asyncio
    async def test_cache_operations(self, redis_client, clean_redis):
        """Тест операций кеширования."""
        cache_manager = CacheManager(redis_client)
        
        # Test basic cache operations
        test_key = "test:cache:key"
        test_value = {"message": "Hello Redis!", "timestamp": datetime.now().isoformat()}
        
        # SET
        await cache_manager.set(test_key, test_value, ttl=60)
        
        # GET
        cached_value = await cache_manager.get(test_key)
        assert cached_value is not None
        assert cached_value["message"] == test_value["message"]
        
        # EXISTS
        exists = await cache_manager.exists(test_key)
        assert exists is True
        
        # DELETE
        await cache_manager.delete(test_key)
        
        # Verify deletion
        deleted_value = await cache_manager.get(test_key)
        assert deleted_value is None

    @pytest.mark.asyncio
    async def test_cache_ttl(self, redis_client, clean_redis):
        """Тест TTL (Time To Live) для кеша."""
        cache_manager = CacheManager(redis_client)
        
        test_key = "test:ttl:key"
        test_value = "This will expire soon"
        
        # Set with short TTL
        await cache_manager.set(test_key, test_value, ttl=1)  # 1 second
        
        # Verify it exists
        value = await cache_manager.get(test_key)
        assert value == test_value
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Verify it expired
        expired_value = await cache_manager.get(test_key)
        assert expired_value is None

    @pytest.mark.asyncio
    async def test_cache_patterns(self, redis_client, clean_redis):
        """Тест паттернов кеширования."""
        cache_manager = CacheManager(redis_client)
        
        # Set multiple keys with pattern
        pattern = "test:pattern:*"
        keys = [f"test:pattern:{i}" for i in range(5)]
        
        for i, key in enumerate(keys):
            await cache_manager.set(key, f"value_{i}", ttl=60)
        
        # Get all keys with pattern
        pattern_keys = await cache_manager.keys(pattern)
        assert len(pattern_keys) == 5
        
        # Delete all keys with pattern
        await cache_manager.delete_pattern(pattern)
        
        # Verify all keys are deleted
        remaining_keys = await cache_manager.keys(pattern)
        assert len(remaining_keys) == 0

    @pytest.mark.asyncio
    async def test_session_management(self, redis_client, clean_redis):
        """Тест управления сессиями."""
        session_manager = SessionManager(redis_client)
        
        user_id = str(uuid.uuid4())
        session_data = {
            "user_id": user_id,
            "email": "test@example.com",
            "role": "user",
            "login_time": datetime.now().isoformat()
        }
        
        # Create session
        session_id = await session_manager.create_session(user_id, session_data)
        assert session_id is not None
        
        # Get session
        retrieved_session = await session_manager.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session["user_id"] == user_id
        assert retrieved_session["email"] == "test@example.com"
        
        # Update session
        updated_data = {"last_activity": datetime.now().isoformat()}
        await session_manager.update_session(session_id, updated_data)
        
        # Verify update
        updated_session = await session_manager.get_session(session_id)
        assert "last_activity" in updated_session
        
        # Delete session
        await session_manager.delete_session(session_id)
        
        # Verify deletion
        deleted_session = await session_manager.get_session(session_id)
        assert deleted_session is None

    @pytest.mark.asyncio
    async def test_pub_sub(self, redis_client, clean_redis):
        """Тест публикации и подписки."""
        channel = "test:channel"
        message = {"type": "test_message", "data": "Hello Pub/Sub!"}
        
        # Subscribe to channel
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        
        # Publish message
        await redis_client.publish(channel, json.dumps(message))
        
        # Receive message
        received_message = None
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                received_message = json.loads(msg["data"])
                break
        
        assert received_message is not None
        assert received_message["type"] == message["type"]
        assert received_message["data"] == message["data"]
        
        await pubsub.unsubscribe(channel)
        await pubsub.close()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, redis_client, clean_redis):
        """Тест ограничения скорости запросов."""
        from app.core.rate_limiter import RateLimiter
        
        rate_limiter = RateLimiter(redis_client)
        
        user_id = str(uuid.uuid4())
        limit = 5
        window = 60  # 60 seconds
        
        # Test rate limiting
        for i in range(limit):
            allowed = await rate_limiter.is_allowed(user_id, limit, window)
            assert allowed is True
        
        # This should be rate limited
        blocked = await rate_limiter.is_allowed(user_id, limit, window)
        assert blocked is False
        
        # Test different user (should not be affected)
        other_user_id = str(uuid.uuid4())
        allowed = await rate_limiter.is_allowed(other_user_id, limit, window)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_distributed_lock(self, redis_client, clean_redis):
        """Тест распределенных блокировок."""
        from app.core.distributed_lock import DistributedLock
        
        lock_manager = DistributedLock(redis_client)
        lock_key = "test:lock:key"
        
        # Acquire lock
        lock_id = await lock_manager.acquire(lock_key, timeout=10)
        assert lock_id is not None
        
        # Try to acquire same lock (should fail)
        second_lock_id = await lock_manager.acquire(lock_key, timeout=1)
        assert second_lock_id is None
        
        # Release lock
        released = await lock_manager.release(lock_key, lock_id)
        assert released is True
        
        # Now we should be able to acquire lock again
        new_lock_id = await lock_manager.acquire(lock_key, timeout=10)
        assert new_lock_id is not None
        
        # Cleanup
        await lock_manager.release(lock_key, new_lock_id)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_client, clean_redis):
        """Тест конкурентных операций с Redis."""
        cache_manager = CacheManager(redis_client)
        
        # Concurrent writes
        async def write_key(key_suffix: int):
            key = f"concurrent:key:{key_suffix}"
            value = f"value_{key_suffix}"
            await cache_manager.set(key, value, ttl=60)
            return key
        
        # Execute concurrent writes
        tasks = [write_key(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 10
        
        # Verify all keys were written
        for i in range(10):
            key = f"concurrent:key:{i}"
            value = await cache_manager.get(key)
            assert value == f"value_{i}"
        
        # Cleanup
        await cache_manager.delete_pattern("concurrent:key:*")

    @pytest.mark.asyncio
    async def test_redis_pipeline(self, redis_client, clean_redis):
        """Тест Redis pipeline для batch операций."""
        # Create pipeline
        pipe = redis_client.pipeline()
        
        # Add multiple operations
        keys = [f"pipeline:key:{i}" for i in range(5)]
        for i, key in enumerate(keys):
            pipe.set(key, f"value_{i}", ex=60)
        
        # Execute pipeline
        results = await pipe.execute()
        
        # Verify all operations succeeded
        assert len(results) == 5
        assert all(result is True for result in results)
        
        # Verify all keys exist
        for key in keys:
            value = await redis_client.get(key)
            assert value is not None
        
        # Cleanup
        await redis_client.delete(*keys)
