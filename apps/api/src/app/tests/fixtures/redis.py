"""
Redis fixtures for integration tests
"""
import pytest
import redis.asyncio as redis
from typing import AsyncGenerator


@pytest.fixture
async def redis_client() -> redis.Redis:
    """Create Redis client for tests"""
    client = redis.Redis(
        host="redis-test",
        port=6379,
        db=1,  # Use test database
        decode_responses=True
    )
    
    try:
        # Test connection
        await client.ping()
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def clean_redis(redis_client: redis.Redis) -> redis.Redis:
    """Clean Redis database before each test"""
    # Flush the test database
    await redis_client.flushdb()
    yield redis_client
    # Clean up after test
    await redis_client.flushdb()
