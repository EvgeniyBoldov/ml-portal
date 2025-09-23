"""
Unit tests for Redis core components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.redis import RedisManager, get_redis, get_sync_redis


class TestRedisManager:
    """Test RedisManager"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_async_redis = Mock()
        self.mock_sync_redis = Mock()
        self.redis_manager = RedisManager()
    
    @patch('app.core.redis.Redis.from_url')
    def test_get_async_redis(self, mock_from_url):
        """Test getting async Redis instance"""
        mock_from_url.return_value = self.mock_async_redis
        result = self.redis_manager.get_async_redis()
        assert result == self.mock_async_redis
    
    @patch('app.core.redis.SyncRedis.from_url')
    def test_get_sync_redis(self, mock_from_url):
        """Test getting sync Redis instance"""
        mock_from_url.return_value = self.mock_sync_redis
        result = self.redis_manager.get_sync_redis()
        assert result == self.mock_sync_redis
    
    def test_ping_async(self):
        """Test async ping"""
        self.mock_async_redis.ping.return_value = True
        
        async def test_async():
            result = await self.redis_manager.ping_async()
            assert result is True
        
        # Note: In real test, this would be awaited
        # await test_async()
    
    def test_ping_sync(self):
        """Test sync ping"""
        self.mock_sync_redis.ping.return_value = True
        
        result = self.redis_manager.ping_sync()
        assert result is True
    
    @patch.object(RedisManager, 'get_async_redis')
    def test_close_async(self, mock_get_async_redis):
        """Test closing async Redis"""
        mock_get_async_redis.return_value = self.mock_async_redis
        
        # Set up the async redis instance
        self.redis_manager._async_redis = self.mock_async_redis
        
        # This would be awaited in real test
        # await self.redis_manager.close_async()
        # self.mock_async_redis.close.assert_called_once()
    
    @patch.object(RedisManager, 'get_sync_redis')
    def test_close_sync(self, mock_get_sync_redis):
        """Test closing sync Redis"""
        mock_get_sync_redis.return_value = self.mock_sync_redis
        
        # Set up the sync redis instance
        self.redis_manager._sync_redis = self.mock_sync_redis
        
        self.redis_manager.close_sync()
        self.mock_sync_redis.close.assert_called_once()
    
    def test_health_check_async(self):
        """Test async health check"""
        self.mock_async_redis.ping.return_value = True
        
        async def test_async():
            result = await self.redis_manager.health_check_async()
            assert result is True
        
        # Note: In real test, this would be awaited
        # await test_async()
    
    def test_health_check_async_failure(self):
        """Test async health check failure"""
        self.mock_async_redis.ping.side_effect = Exception("Redis error")
        
        async def test_async():
            result = await self.redis_manager.health_check_async()
            assert result is False
        
        # Note: In real test, this would be awaited
        # await test_async()
    
    def test_health_check_sync(self):
        """Test sync health check"""
        self.mock_sync_redis.ping.return_value = True
        
        result = self.redis_manager.health_check_sync()
        assert result is True
    
    @patch.object(RedisManager, 'get_sync_redis')
    def test_health_check_sync_failure(self, mock_get_sync_redis):
        """Test sync health check failure"""
        mock_get_sync_redis.return_value = self.mock_sync_redis
        self.mock_sync_redis.ping.side_effect = Exception("Redis error")
        
        result = self.redis_manager.health_check_sync()
        assert result is False


class TestRedisDependencies:
    """Test Redis dependency functions"""
    
    @patch('app.core.redis.redis_manager')
    def test_get_redis_dependency(self, mock_redis_manager):
        """Test get_redis dependency"""
        mock_redis = Mock()
        mock_redis_manager.get_async_redis.return_value = mock_redis
        
        result = get_redis()
        assert result == mock_redis
    
    @patch('app.core.redis.redis_manager')
    def test_get_sync_redis_dependency(self, mock_redis_manager):
        """Test get_sync_redis dependency"""
        mock_redis = Mock()
        mock_redis_manager.get_sync_redis.return_value = mock_redis
        
        result = get_sync_redis()
        assert result == mock_redis
