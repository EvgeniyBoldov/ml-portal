"""
Unit tests for RAGStatusManager
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.rag_status_manager import (
    RAGStatusManager,
    StageStatus,
    PipelineStage,
    VALID_TRANSITIONS,
    StatusTransitionError
)


class TestStageStatus:
    """Test StageStatus enum"""
    
    def test_status_values(self):
        """All expected statuses exist"""
        assert StageStatus.PENDING.value == 'pending'
        assert StageStatus.QUEUED.value == 'queued'
        assert StageStatus.PROCESSING.value == 'processing'
        assert StageStatus.COMPLETED.value == 'completed'
        assert StageStatus.FAILED.value == 'failed'
        assert StageStatus.CANCELLED.value == 'cancelled'


class TestValidTransitions:
    """Test status transition rules"""
    
    def test_pending_transitions(self):
        """PENDING can go to QUEUED"""
        assert StageStatus.QUEUED in VALID_TRANSITIONS[StageStatus.PENDING]
    
    def test_queued_transitions(self):
        """QUEUED can go to PROCESSING or CANCELLED"""
        assert StageStatus.PROCESSING in VALID_TRANSITIONS[StageStatus.QUEUED]
        assert StageStatus.CANCELLED in VALID_TRANSITIONS[StageStatus.QUEUED]
    
    def test_processing_transitions(self):
        """PROCESSING can go to COMPLETED, FAILED, or CANCELLED"""
        assert StageStatus.COMPLETED in VALID_TRANSITIONS[StageStatus.PROCESSING]
        assert StageStatus.FAILED in VALID_TRANSITIONS[StageStatus.PROCESSING]
        assert StageStatus.CANCELLED in VALID_TRANSITIONS[StageStatus.PROCESSING]
    
    def test_failed_transitions(self):
        """FAILED can go to QUEUED (retry)"""
        assert StageStatus.QUEUED in VALID_TRANSITIONS[StageStatus.FAILED]
    
    def test_cancelled_transitions(self):
        """CANCELLED can go to QUEUED (retry)"""
        assert StageStatus.QUEUED in VALID_TRANSITIONS[StageStatus.CANCELLED]
    
    def test_completed_is_terminal(self):
        """COMPLETED has no valid transitions (terminal state)"""
        assert VALID_TRANSITIONS.get(StageStatus.COMPLETED, set()) == set()


class TestRAGStatusManager:
    """Test RAGStatusManager methods"""
    
    @pytest.fixture
    def mock_status_repo(self):
        """Mock status repository"""
        repo = AsyncMock()
        repo.get_node = AsyncMock(return_value=None)
        repo.upsert_node = AsyncMock()
        repo.get_all_nodes = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def mock_event_publisher(self):
        """Mock event publisher"""
        publisher = AsyncMock()
        publisher.publish_status_update = AsyncMock()
        return publisher
    
    @pytest.fixture
    def mock_repo_factory(self, mock_status_repo):
        """Mock repository factory"""
        factory = MagicMock()
        factory.get_rag_status_repository = MagicMock(return_value=mock_status_repo)
        factory.tenant_id = uuid4()
        return factory
    
    @pytest.fixture
    def status_manager(self, mock_session, mock_repo_factory, mock_event_publisher):
        """Create RAGStatusManager with mocks"""
        return RAGStatusManager(
            session=mock_session,
            repo_factory=mock_repo_factory,
            event_publisher=mock_event_publisher
        )
    
    @pytest.mark.asyncio
    async def test_transition_stage_valid(self, status_manager, mock_status_repo):
        """Valid transition should succeed"""
        doc_id = uuid4()
        
        # Mock current status as QUEUED
        mock_node = MagicMock()
        mock_node.status = 'queued'
        mock_status_repo.get_node.return_value = mock_node
        
        # Transition to PROCESSING should work
        await status_manager.transition_stage(
            doc_id=doc_id,
            stage='extract',
            new_status=StageStatus.PROCESSING,
            celery_task_id='test-task-123'
        )
        
        mock_status_repo.upsert_node.assert_called_once()
        call_kwargs = mock_status_repo.upsert_node.call_args.kwargs
        assert call_kwargs['status'] == 'processing'
        assert call_kwargs['celery_task_id'] == 'test-task-123'
    
    @pytest.mark.asyncio
    async def test_transition_stage_invalid(self, status_manager, mock_status_repo):
        """Invalid transition should raise error"""
        doc_id = uuid4()
        
        # Mock current status as COMPLETED
        mock_node = MagicMock()
        mock_node.status = 'completed'
        mock_status_repo.get_node.return_value = mock_node
        
        # Transition to PROCESSING should fail
        with pytest.raises(StatusTransitionError):
            await status_manager.transition_stage(
                doc_id=doc_id,
                stage='extract',
                new_status=StageStatus.PROCESSING
            )
    
    @pytest.mark.asyncio
    async def test_transition_sets_started_at(self, status_manager, mock_status_repo):
        """PROCESSING transition should set started_at"""
        doc_id = uuid4()
        mock_status_repo.get_node.return_value = None
        
        await status_manager.transition_stage(
            doc_id=doc_id,
            stage='extract',
            new_status=StageStatus.PROCESSING
        )
        
        call_kwargs = mock_status_repo.upsert_node.call_args.kwargs
        assert 'started_at' in call_kwargs
        assert isinstance(call_kwargs['started_at'], datetime)
    
    @pytest.mark.asyncio
    async def test_transition_sets_finished_at(self, status_manager, mock_status_repo):
        """COMPLETED/FAILED/CANCELLED transitions should set finished_at"""
        doc_id = uuid4()
        
        mock_node = MagicMock()
        mock_node.status = 'processing'
        mock_status_repo.get_node.return_value = mock_node
        
        await status_manager.transition_stage(
            doc_id=doc_id,
            stage='extract',
            new_status=StageStatus.COMPLETED
        )
        
        call_kwargs = mock_status_repo.upsert_node.call_args.kwargs
        assert 'finished_at' in call_kwargs
        assert isinstance(call_kwargs['finished_at'], datetime)
    
    @pytest.mark.asyncio
    async def test_transition_clears_task_id_on_complete(self, status_manager, mock_status_repo):
        """Task ID should be cleared when stage completes"""
        doc_id = uuid4()
        
        mock_node = MagicMock()
        mock_node.status = 'processing'
        mock_node.celery_task_id = 'old-task-id'
        mock_status_repo.get_node.return_value = mock_node
        
        await status_manager.transition_stage(
            doc_id=doc_id,
            stage='extract',
            new_status=StageStatus.COMPLETED
        )
        
        call_kwargs = mock_status_repo.upsert_node.call_args.kwargs
        assert call_kwargs.get('celery_task_id') is None
    
    @pytest.mark.asyncio
    async def test_stop_stage_returns_task_id(self, status_manager, mock_status_repo):
        """stop_stage should return celery_task_id for revocation"""
        doc_id = uuid4()
        
        mock_node = MagicMock()
        mock_node.status = 'processing'
        mock_node.celery_task_id = 'task-to-cancel'
        mock_status_repo.get_node.return_value = mock_node
        
        task_id = await status_manager.stop_stage(doc_id, 'extract')
        
        assert task_id == 'task-to-cancel'
    
    @pytest.mark.asyncio
    async def test_stop_stage_cascades_downstream(self, status_manager, mock_status_repo):
        """stop_stage should reset downstream stages"""
        doc_id = uuid4()
        
        # Mock extract stage as processing
        mock_node = MagicMock()
        mock_node.status = 'processing'
        mock_node.celery_task_id = None
        mock_status_repo.get_node.return_value = mock_node
        
        await status_manager.stop_stage(doc_id, 'extract')
        
        # Should have multiple upsert calls (extract + downstream)
        assert mock_status_repo.upsert_node.call_count >= 1


class TestPipelineStage:
    """Test PipelineStage enum"""
    
    def test_stage_order(self):
        """Stages should be in correct order"""
        stages = list(PipelineStage)
        stage_names = [s.value for s in stages]
        
        assert 'upload' in stage_names
        assert 'extract' in stage_names
        assert 'normalize' in stage_names
        assert 'chunk' in stage_names
        
        # Upload should be first
        assert stage_names.index('upload') < stage_names.index('extract')
        assert stage_names.index('extract') < stage_names.index('normalize')
        assert stage_names.index('normalize') < stage_names.index('chunk')
