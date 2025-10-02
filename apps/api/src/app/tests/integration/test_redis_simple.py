"""
Простые интеграционные тесты для Redis.
Использует реальный Redis для проверки базовых операций.
"""
import pytest
import asyncio
import json
import redis.asyncio as redis


@pytest.mark.integration
class TestRedisIntegration:
    """Интеграционные тесты для Redis."""

    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """Тест подключения к Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Test basic connection
            result = await client.ping()
            assert result is True
            
            # Test set/get
            await client.set("test_key", "test_value")
            value = await client.get("test_key")
            assert value == "test_value"
            
            # Cleanup
            await client.delete("test_key")
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_operations(self):
        """Тест базовых операций Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Test string operations
            await client.set("string_key", "string_value", ex=60)
            value = await client.get("string_key")
            assert value == "string_value"
            
            # Test exists
            exists = await client.exists("string_key")
            assert exists == 1
            
            # Test delete
            await client.delete("string_key")
            value = await client.get("string_key")
            assert value is None
            
            # Test hash operations
            await client.hset("hash_key", mapping={"field1": "value1", "field2": "value2"})
            hash_value = await client.hget("hash_key", "field1")
            assert hash_value == "value1"
            
            # Test list operations
            await client.lpush("list_key", "item1", "item2", "item3")
            list_length = await client.llen("list_key")
            assert list_length == 3
            
            # Test set operations
            await client.sadd("set_key", "member1", "member2", "member3")
            set_members = await client.smembers("set_key")
            assert len(set_members) == 3
            assert "member1" in set_members
            
            # Cleanup
            await client.delete("string_key", "hash_key", "list_key", "set_key")
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_json_operations(self):
        """Тест JSON операций Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Test JSON data
            test_data = {
                "name": "test_user",
                "age": 25,
                "email": "test@example.com",
                "metadata": {"role": "user", "active": True}
            }
            
            # Store JSON
            await client.set("json_key", json.dumps(test_data))
            
            # Retrieve JSON
            json_value = await client.get("json_key")
            retrieved_data = json.loads(json_value)
            
            assert retrieved_data["name"] == "test_user"
            assert retrieved_data["age"] == 25
            assert retrieved_data["metadata"]["role"] == "user"
            
            # Cleanup
            await client.delete("json_key")
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_ttl(self):
        """Тест TTL (Time To Live) для Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Set key with TTL
            await client.set("ttl_key", "ttl_value", ex=2)  # 2 seconds
            
            # Check TTL
            ttl = await client.ttl("ttl_key")
            assert ttl > 0
            assert ttl <= 2
            
            # Verify key exists
            value = await client.get("ttl_key")
            assert value == "ttl_value"
            
            # Wait for expiration
            await asyncio.sleep(3)
            
            # Verify key expired
            value = await client.get("ttl_key")
            assert value is None
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_patterns(self):
        """Тест паттернов Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Set multiple keys with pattern
            keys = [f"pattern:key:{i}" for i in range(5)]
            for i, key in enumerate(keys):
                await client.set(key, f"value_{i}")
            
            # Get all keys with pattern
            pattern_keys = await client.keys("pattern:key:*")
            assert len(pattern_keys) == 5
            
            # Delete all keys with pattern
            for key in pattern_keys:
                await client.delete(key)
            
            # Verify all keys are deleted
            remaining_keys = await client.keys("pattern:key:*")
            assert len(remaining_keys) == 0
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_pipeline(self):
        """Тест Redis pipeline для batch операций."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Create pipeline
            pipe = client.pipeline()
            
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
                value = await client.get(key)
                assert value is not None
            
            # Cleanup
            await client.delete(*keys)
            
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_redis_concurrent_operations(self):
        """Тест конкурентных операций с Redis."""
        client = redis.from_url("redis://redis-test:6379", decode_responses=True)
        
        try:
            # Concurrent writes
            async def write_key(key_suffix: int):
                key = f"concurrent:key:{key_suffix}"
                value = f"value_{key_suffix}"
                await client.set(key, value, ex=60)
                return key
            
            # Execute concurrent writes
            tasks = [write_key(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 10
            
            # Verify all keys were written
            for i in range(10):
                key = f"concurrent:key:{i}"
                value = await client.get(key)
                assert value == f"value_{i}"
            
            # Cleanup
            keys_to_delete = [f"concurrent:key:{i}" for i in range(10)]
            await client.delete(*keys_to_delete)
            
        finally:
            await client.close()
