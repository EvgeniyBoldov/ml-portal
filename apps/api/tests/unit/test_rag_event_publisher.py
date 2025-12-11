"""
Unit tests for RAGEventPublisher
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.rag_event_publisher import RAGEventPublisher


class TestRAGEventPublisher:
    """Test RAGEventPublisher"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis = AsyncMock()
        redis.publish = AsyncMock(return_value=1)
        return redis
    
    @pytest.fixture
    def publisher(self, mock_redis):
        """Create publisher with mock redis"""
        return RAGEventPublisher(mock_redis)
    
    @pytest.mark.asyncio
    async def test_publish_status_update(self, publisher, mock_redis):
        """Should publish to correct channels"""
        doc_id = uuid4()
        tenant_id = uuid4()
        
        await publisher.publish_status_update(
            doc_id=doc_id,
            tenant_id=tenant_id,
            stage='extract',
            status='processing',
            metrics={'word_count': 100}
        )
        
        # Should publish to admin and tenant channels
        assert mock_redis.publish.call_count >= 2
        
        # Check channel names
        call_args_list = mock_redis.publish.call_args_list
        channels = [call[0][0] for call in call_args_list]
        
        assert 'rag:status:admin' in channels
        assert f'rag:status:tenant:{tenant_id}' in channels
    
    @pytest.mark.asyncio
    async def test_publish_message_format(self, publisher, mock_redis):
        """Published message should have correct format"""
        doc_id = uuid4()
        tenant_id = uuid4()
        
        await publisher.publish_status_update(
            doc_id=doc_id,
            tenant_id=tenant_id,
            stage='extract',
            status='completed',
            metrics={'duration_sec': 1.5}
        )
        
        # Get published message
        call_args = mock_redis.publish.call_args_list[0]
        message = call_args[0][1]
        
        # Should be valid JSON
        data = json.loads(message)
        
        assert data['type'] == 'rag.status'
        assert data['doc_id'] == str(doc_id)
        assert data['stage'] == 'extract'
        assert data['status'] == 'completed'
        assert data['metrics'] == {'duration_sec': 1.5}
    
    @pytest.mark.asyncio
    async def test_publish_embed_progress(self, publisher, mock_redis):
        """Should publish embed progress events"""
        doc_id = uuid4()
        tenant_id = uuid4()
        
        await publisher.publish_embed_progress(
            doc_id=doc_id,
            tenant_id=tenant_id,
            model_alias='text-embedding-ada-002',
            done=50,
            total=100
        )
        
        call_args = mock_redis.publish.call_args_list[0]
        message = call_args[0][1]
        data = json.loads(message)
        
        assert data['type'] == 'rag.embed.progress'
        assert data['model_alias'] == 'text-embedding-ada-002'
        assert data['done'] == 50
        assert data['total'] == 100
    
    @pytest.mark.asyncio
    async def test_publish_tags_updated(self, publisher, mock_redis):
        """Should publish tags updated events"""
        doc_id = uuid4()
        tenant_id = uuid4()
        
        await publisher.publish_tags_updated(
            doc_id=doc_id,
            tenant_id=tenant_id,
            tags=['test', 'updated']
        )
        
        call_args = mock_redis.publish.call_args_list[0]
        message = call_args[0][1]
        data = json.loads(message)
        
        assert data['type'] == 'rag.tags.updated'
        assert data['tags'] == ['test', 'updated']
    
    @pytest.mark.asyncio
    async def test_publish_deleted(self, publisher, mock_redis):
        """Should publish document deleted events"""
        doc_id = uuid4()
        tenant_id = uuid4()
        
        await publisher.publish_deleted(
            doc_id=doc_id,
            tenant_id=tenant_id
        )
        
        call_args = mock_redis.publish.call_args_list[0]
        message = call_args[0][1]
        data = json.loads(message)
        
        assert data['type'] == 'rag.deleted'
        assert data['doc_id'] == str(doc_id)
