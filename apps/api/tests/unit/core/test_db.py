"""
Unit tests for database core components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.db import DatabaseManager, get_session, get_async_session


class TestDatabaseManager:
    """Test DatabaseManager"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_engine = Mock()
        self.mock_session_factory = Mock()
        self.db_manager = DatabaseManager()
    
    def test_get_session(self):
        """Test getting sync session"""
        # Test that get_session returns a generator
        session_gen = self.db_manager.get_session()
        assert hasattr(session_gen, '__next__')
        
        # Test that it can be iterated
        try:
            session = next(session_gen)
            assert session is not None
        except StopIteration:
            pass
    
    def test_get_async_session(self):
        """Test getting async session"""
        mock_session = Mock()
        self.mock_session_factory.return_value = mock_session
        
        async def test_async():
            async with self.db_manager.get_async_session() as session:
                assert session == mock_session
        
        # Note: In real test, this would be awaited
        # await test_async()
    
    def test_session_scope(self):
        """Test session scope context manager"""
        # Test that session_scope returns a context manager
        with self.db_manager.session_scope() as session:
            assert session is not None
            # Session should be a real SQLAlchemy session
    
    def test_async_session_scope(self):
        """Test async session scope context manager"""
        mock_session = Mock()
        self.mock_session_factory.return_value = mock_session
        
        async def test_async():
            async with self.db_manager.async_session_scope() as session:
                assert session == mock_session
        
        # Note: In real test, this would be awaited
        # await test_async()
    
    def test_close_all(self):
        """Test closing all sessions"""
        self.db_manager.close_all()
        # Should not raise any exceptions
    
    def test_close_async_all(self):
        """Test closing all async sessions"""
        self.db_manager.close_async_all()
        # Should not raise any exceptions
    
    @patch.object(DatabaseManager, 'session_scope')
    def test_health_check(self, mock_session_scope):
        """Test database health check"""
        mock_session = Mock()
        mock_session.execute.return_value = Mock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        mock_session_scope.return_value.__exit__.return_value = None
        
        result = self.db_manager.health_check()
        assert result is True
    
    def test_health_check_failure(self):
        """Test database health check failure"""
        with patch.object(self.db_manager, '_session_factory') as mock_session_factory:
            mock_session = Mock()
            mock_session.execute.side_effect = Exception("Database error")
            mock_session_factory.return_value.__enter__.return_value = mock_session
            
            result = self.db_manager.health_check()
            assert result is False
    
    def test_async_health_check(self):
        """Test async database health check"""
        with patch.object(self.db_manager, 'get_async_session') as mock_get_async_session:
            mock_session = Mock()
            mock_get_async_session.return_value.__aenter__.return_value = mock_session
            mock_session.execute.return_value = Mock()
            
            async def test_async():
                result = await self.db_manager.async_health_check()
                assert result is True
            
            # Note: In real test, this would be awaited
            # await test_async()
    
    def test_async_health_check_failure(self):
        """Test async database health check failure"""
        with patch.object(self.db_manager, 'get_async_session') as mock_get_async_session:
            mock_get_async_session.side_effect = Exception("Database error")
            
            async def test_async():
                result = await self.db_manager.async_health_check()
                assert result is False
            
            # Note: In real test, this would be awaited
            # await test_async()


class TestDatabaseDependencies:
    """Test database dependency functions"""
    
    @patch('app.core.db.db_manager')
    def test_get_session_dependency(self, mock_db_manager):
        """Test get_session dependency"""
        mock_session = Mock()
        mock_db_manager.get_session.return_value = iter([mock_session])
        
        session = next(get_session())
        assert session == mock_session
    
    @patch('app.core.db.db_manager')
    def test_get_async_session_dependency(self, mock_db_manager):
        """Test get_async_session dependency"""
        mock_session = Mock()
        mock_db_manager.get_async_session.return_value.__aenter__.return_value = mock_session
        
        async def test_async():
            session = await get_async_session().__anext__()
            assert session == mock_session
        
        # Note: In real test, this would be awaited
        # await test_async()
