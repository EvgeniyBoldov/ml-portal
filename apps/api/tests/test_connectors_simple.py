"""
Simple tests for core connectors without main.py dependencies
"""
import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.core.redis import redis_manager, RedisManager
from app.core.cache import cache, CacheManager
from app.core.s3 import s3_manager, S3Manager


class TestRedisManager:
    """Test Redis connection manager"""
    
    def test_redis_manager_initialization(self):
        """Test Redis manager initialization"""
        assert isinstance(redis_manager, RedisManager)
        assert redis_manager._async_redis is None
        assert redis_manager._sync_redis is None
    
    def test_get_async_redis(self):
        """Test getting async Redis client"""
        with patch('redis.asyncio.Redis.from_url') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            client = redis_manager.get_async_redis()
            assert client == mock_client
            assert redis_manager._async_redis == mock_client
    
    def test_get_sync_redis(self):
        """Test getting sync Redis client"""
        with patch('redis.Redis.from_url') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            client = redis_manager.get_sync_redis()
            assert client == mock_client
            assert redis_manager._sync_redis == mock_client
    
    @pytest.mark.asyncio
    async def test_ping_async_success(self):
        """Test async ping success"""
        with patch.object(redis_manager, 'get_async_redis') as mock_get_redis:
            mock_client = Mock()
            # Make ping return a coroutine
            async def mock_ping():
                return True
            mock_client.ping = mock_ping
            mock_get_redis.return_value = mock_client
            
            result = await redis_manager.ping_async()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_ping_async_failure(self):
        """Test async ping failure"""
        with patch.object(redis_manager, 'get_async_redis') as mock_get_redis:
            mock_client = Mock()
            # Make ping raise an exception
            async def mock_ping():
                raise Exception("Connection failed")
            mock_client.ping = mock_ping
            mock_get_redis.return_value = mock_client
            
            result = await redis_manager.ping_async()
            assert result is False
    
    def test_ping_sync_success(self):
        """Test sync ping success"""
        with patch.object(redis_manager, 'get_sync_redis') as mock_get_redis:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_get_redis.return_value = mock_client
            
            result = redis_manager.ping_sync()
            assert result is True
    
    def test_ping_sync_failure(self):
        """Test sync ping failure"""
        with patch.object(redis_manager, 'get_sync_redis') as mock_get_redis:
            mock_client = Mock()
            mock_client.ping.side_effect = Exception("Connection failed")
            mock_get_redis.return_value = mock_client
            
            result = redis_manager.ping_sync()
            assert result is False


class TestCacheManager:
    """Test cache manager"""
    
    def test_cache_manager_initialization(self):
        """Test cache manager initialization"""
        assert isinstance(cache, CacheManager)
        assert cache.default_ttl == 3600
        assert cache._redis_manager == redis_manager
    
    def test_serialize_deserialize(self):
        """Test serialization and deserialization"""
        test_data = {"key": "value", "number": 123}
        
        serialized = cache._serialize(test_data)
        assert isinstance(serialized, str)
        
        deserialized = cache._deserialize(serialized)
        assert deserialized == test_data
    
    def test_get_set_sync(self):
        """Test sync get/set operations"""
        with patch.object(cache, '_redis_manager') as mock_redis_manager:
            mock_redis = Mock()
            mock_redis_manager.get_sync_redis.return_value = mock_redis
            
            # Test set
            mock_redis.setex.return_value = True
            result = cache.set("test_key", "test_value", 60)
            assert result is True
            mock_redis.setex.assert_called_once()
            
            # Test get
            mock_redis.get.return_value = cache._serialize("test_value")
            result = cache.get("test_key")
            assert result == "test_value"
    
    @pytest.mark.asyncio
    async def test_get_set_async(self):
        """Test async get/set operations"""
        with patch.object(cache, '_redis_manager') as mock_redis_manager:
            mock_redis = Mock()
            mock_redis_manager.get_async_redis.return_value = mock_redis
            
            # Test set
            async def mock_setex(key, ttl, value):
                return True
            mock_redis.setex = mock_setex
            result = await cache.set_async("test_key", "test_value", 60)
            assert result is True
            
            # Test get
            async def mock_get(key):
                return cache._serialize("test_value")
            mock_redis.get = mock_get
            result = await cache.get_async("test_key")
            assert result == "test_value"
    
    def test_get_or_set_sync(self):
        """Test sync get_or_set operation"""
        with patch.object(cache, 'get') as mock_get:
            mock_get.return_value = None
            
            def factory_func():
                return "generated_value"
            
            with patch.object(cache, 'set') as mock_set:
                mock_set.return_value = True
                
                result = cache.get_or_set("test_key", factory_func, 60)
                assert result == "generated_value"
                mock_set.assert_called_once_with("test_key", "generated_value", 60)
    
    @pytest.mark.asyncio
    async def test_get_or_set_async(self):
        """Test async get_or_set operation"""
        with patch.object(cache, 'get_async') as mock_get:
            mock_get.return_value = None
            
            async def factory_func():
                return "generated_value"
            
            with patch.object(cache, 'set_async') as mock_set:
                mock_set.return_value = True
                
                result = await cache.get_or_set_async("test_key", factory_func, 60)
                assert result == "generated_value"
                mock_set.assert_called_once_with("test_key", "generated_value", 60)


class TestS3Manager:
    """Test S3 manager"""
    
    def test_s3_manager_initialization(self):
        """Test S3 manager initialization"""
        assert isinstance(s3_manager, S3Manager)
        assert s3_manager._client is None
        assert s3_manager._endpoint is not None
        assert s3_manager._access_key is not None
        assert s3_manager._secret_key is not None
    
    def test_health_check_success(self):
        """Test S3 health check success"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.list_buckets.return_value = []
            mock_get_client.return_value = mock_client
            
            result = s3_manager.health_check()
            assert result is True
    
    def test_health_check_failure(self):
        """Test S3 health check failure"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.list_buckets.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client
            
            result = s3_manager.health_check()
            assert result is False
    
    def test_ensure_bucket_exists(self):
        """Test ensuring bucket exists when it already exists"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.bucket_exists.return_value = True
            mock_get_client.return_value = mock_client
            
            result = s3_manager.ensure_bucket("test-bucket")
            assert result is True
            mock_client.make_bucket.assert_not_called()
    
    def test_ensure_bucket_create(self):
        """Test ensuring bucket exists when it doesn't exist"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.bucket_exists.return_value = False
            mock_client.make_bucket.return_value = None
            mock_get_client.return_value = mock_client
            
            result = s3_manager.ensure_bucket("test-bucket")
            assert result is True
            mock_client.make_bucket.assert_called_once_with("test-bucket")
    
    def test_put_object_success(self):
        """Test successful object upload"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            with patch.object(s3_manager, 'ensure_bucket') as mock_ensure_bucket:
                mock_client = Mock()
                mock_client.put_object.return_value = Mock()
                mock_get_client.return_value = mock_client
                mock_ensure_bucket.return_value = True
                
                result = s3_manager.put_object("test-bucket", "test-key", b"test-data")
                assert result is True
                mock_ensure_bucket.assert_called_once_with("test-bucket")
                mock_client.put_object.assert_called_once()
    
    def test_put_object_failure(self):
        """Test failed object upload"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            with patch.object(s3_manager, 'ensure_bucket') as mock_ensure_bucket:
                mock_client = Mock()
                mock_client.put_object.side_effect = Exception("Upload failed")
                mock_get_client.return_value = mock_client
                mock_ensure_bucket.return_value = True
                
                result = s3_manager.put_object("test-bucket", "test-key", b"test-data")
                assert result is False
    
    def test_get_object_success(self):
        """Test successful object download"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_object = Mock()
            mock_client.get_object.return_value = mock_object
            mock_get_client.return_value = mock_client
            
            result = s3_manager.get_object("test-bucket", "test-key")
            assert result == mock_object
            mock_client.get_object.assert_called_once_with("test-bucket", "test-key")
    
    def test_get_object_not_found(self):
        """Test object not found"""
        from minio.error import S3Error
        
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            s3_error = S3Error("NoSuchKey", "The specified key does not exist", "", "", "", "")
            mock_client.get_object.side_effect = s3_error
            mock_get_client.return_value = mock_client
            
            result = s3_manager.get_object("test-bucket", "test-key")
            assert result is None
    
    def test_presign_put_success(self):
        """Test successful presigned PUT URL generation"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.presigned_put_object.return_value = "https://example.com/presigned-url"
            mock_get_client.return_value = mock_client
            
            result = s3_manager.presign_put("test-bucket", "test-key", 3600)
            assert result == "https://example.com/presigned-url"
            mock_client.presigned_put_object.assert_called_once()
    
    def test_presign_put_failure(self):
        """Test failed presigned PUT URL generation"""
        with patch.object(s3_manager, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.presigned_put_object.side_effect = Exception("Presign failed")
            mock_get_client.return_value = mock_client
            
            result = s3_manager.presign_put("test-bucket", "test-key", 3600)
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
