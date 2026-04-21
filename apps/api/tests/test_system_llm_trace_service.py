"""
Unit tests for SystemLLMTraceService.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock

from app.models.system_llm_trace import SystemLLMTrace, SystemLLMTraceType
from app.repositories.system_llm_trace_repository import SystemLLMTraceRepository
from app.services.system_llm_trace_service import SystemLLMTraceService


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_repo():
    """Mock SystemLLMTraceRepository."""
    return AsyncMock(spec=SystemLLMTraceRepository)


@pytest.fixture
def trace_service(mock_session, mock_repo):
    """SystemLLMTraceService with mocked dependencies."""
    service = SystemLLMTraceService(mock_session)
    service.repo = mock_repo
    return service


@pytest.fixture
def sample_role_config():
    """Sample role configuration."""
    return {
        "id": str(uuid.uuid4()),
        "role_type": "triage",
        "identity": "You are a Triage Agent",
        "mission": "Determine next action",
        "rules": "Analyze user message",
        "safety": "Never choose final for internal systems",
        "output_requirements": "Return strict JSON",
        "examples": [],
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.0,
        "max_tokens": 1000,
        "timeout_s": 10,
        "max_retries": 2,
        "retry_backoff": "linear",
        "prompt": "# IDENTITY\nYou are a Triage Agent\n\n# MISSION\nDetermine next action"
    }


@pytest.fixture
def sample_structured_input():
    """Sample structured input for triage."""
    return {
        "user_message": "Create business plan",
        "conversation_summary": "User wants help with business planning",
        "session_state": {"status": "active"},
        "available_agents": [{"slug": "business-planner"}],
        "policies": "default",
        "active_run": None
    }


@pytest.fixture
def sample_messages():
    """Sample messages for LLM."""
    return [
        {"role": "system", "content": "# IDENTITY\nYou are a Triage Agent"},
        {"role": "user", "content": '{"user_message": "Create business plan"}'}
    ]


class TestSystemLLMTraceService:
    """Test cases for SystemLLMTraceService."""
    
    @pytest.mark.asyncio
    async def test_create_trace_success(
        self, trace_service, mock_repo, sample_role_config,
        sample_structured_input, sample_messages
    ):
        """Test successful trace creation."""
        # Setup
        mock_trace = Mock(spec=SystemLLMTrace)
        mock_trace.id = uuid.uuid4()
        mock_repo.create.return_value = mock_trace
        
        # Execute
        result = await trace_service.create_trace(
            trace_type=SystemLLMTraceType.TRIAGE,
            role_config=sample_role_config,
            structured_input=sample_structured_input,
            messages_sent=sample_messages,
            raw_response='{"type": "plan", "confidence": 0.9}',
            parsed_response={"type": "plan", "confidence": 0.9},
            validation_status="success",
            duration_ms=3500,
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=1000,
            attempt_number=1,
            total_attempts=1,
            result_type="plan",
            result_summary="Routed to planner",
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4()
        )
        
        # Verify
        assert result == mock_trace
        mock_repo.create.assert_called_once()
        
        # Check the trace object passed to create
        call_args = mock_repo.create.call_args[0][0]
        assert isinstance(call_args, SystemLLMTrace)
        assert call_args.trace_type == SystemLLMTraceType.TRIAGE
        assert call_args.validation_status == "success"
        assert call_args.model == "llama-3.3-70b-versatile"
        assert call_args.duration_ms == 3500
        assert call_args.compiled_prompt_hash is not None
        assert len(call_args.compiled_prompt_hash) == 16  # SHA-256 hash truncated
    
    @pytest.mark.asyncio
    async def test_create_trace_with_fallback(
        self, trace_service, mock_repo, sample_role_config,
        sample_structured_input, sample_messages
    ):
        """Test trace creation with fallback applied."""
        # Setup
        mock_trace = Mock(spec=SystemLLMTrace)
        mock_repo.create.return_value = mock_trace
        
        fallback_details = {"original_response": {"type": "final"}, "error": "Invalid type"}
        
        # Execute
        result = await trace_service.create_trace(
            trace_type=SystemLLMTraceType.TRIAGE,
            role_config=sample_role_config,
            structured_input=sample_structured_input,
            messages_sent=sample_messages,
            raw_response='{"type": "final"}',
            parsed_response={"type": "plan", "confidence": 0.9},
            validation_status="fallback_applied",
            duration_ms=3500,
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=1000,
            attempt_number=1,
            total_attempts=1,
            validation_error="Invalid type",
            fallback_applied=True,
            fallback_details=fallback_details,
            result_type="plan",
            result_summary="Routed to planner",
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4()
        )
        
        # Verify
        assert result == mock_trace
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.fallback_applied is True
        assert call_args.fallback_details == fallback_details
        assert call_args.validation_status == "fallback_applied"
    
    @pytest.mark.asyncio
    async def test_create_trace_from_execution(
        self, trace_service, mock_repo, sample_role_config,
        sample_structured_input, sample_messages
    ):
        """Test convenience method create_trace_from_execution."""
        # Setup
        mock_trace = Mock(spec=SystemLLMTrace)
        mock_repo.create.return_value = mock_trace
        
        start_time = datetime.now(timezone.utc).timestamp() - 3.5  # 3.5 seconds ago
        
        # Execute
        result = await trace_service.create_trace_from_execution(
            trace_type=SystemLLMTraceType.TRIAGE,
            role_config=sample_role_config,
            structured_input=sample_structured_input,
            messages=sample_messages,
            llm_response='{"type": "plan"}',
            parsed_response={"type": "plan"},
            validation_status="success",
            start_time=start_time,
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=1000,
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4()
        )
        
        # Verify
        assert result == mock_trace
        mock_repo.create.assert_called_once()
        
        # Check duration calculation
        call_args = mock_repo.create.call_args[0][0]
        assert call_args.duration_ms > 3000  # Should be around 3500ms
        assert call_args.duration_ms < 4000
    
    @pytest.mark.asyncio
    async def test_get_trace(self, trace_service, mock_repo):
        """Test getting trace by ID."""
        # Setup
        trace_id = uuid.uuid4()
        mock_trace = Mock(spec=SystemLLMTrace)
        mock_repo.get_by_id.return_value = mock_trace
        
        # Execute
        result = await trace_service.get_trace(trace_id)
        
        # Verify
        assert result == mock_trace
        mock_repo.get_by_id.assert_called_once_with(trace_id)
    
    @pytest.mark.asyncio
    async def test_get_chat_traces(self, trace_service, mock_repo):
        """Test getting traces for a chat."""
        # Setup
        chat_id = uuid.uuid4()
        mock_traces = [Mock(spec=SystemLLMTrace) for _ in range(3)]
        mock_repo.get_by_chat_id.return_value = mock_traces
        
        # Execute
        result = await trace_service.get_chat_traces(chat_id, trace_type="triage", limit=50)
        
        # Verify
        assert result == mock_traces
        mock_repo.get_by_chat_id.assert_called_once_with(chat_id, "triage", 50)
    
    @pytest.mark.asyncio
    async def test_cleanup_old_traces(self, trace_service, mock_repo):
        """Test cleanup of old traces."""
        # Setup
        mock_repo.delete_older_than.return_value = 42
        
        # Execute
        result = await trace_service.cleanup_old_traces(days=14)
        
        # Verify
        assert result == 42
        mock_repo.delete_older_than.assert_called_once()
        
        # Check the cutoff date
        call_args = mock_repo.delete_older_than.call_args[0]
        cutoff_date = call_args[0]
        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        assert abs((cutoff_date - expected_cutoff).total_seconds()) < 60  # Within 1 minute
    
    @pytest.mark.asyncio
    async def test_get_trace_statistics(self, trace_service, mock_repo):
        """Test getting trace statistics."""
        # Setup
        tenant_id = uuid.uuid4()
        mock_stats = {
            "triage_success": {"count": 10, "avg_duration_ms": 3500},
            "planner_failed": {"count": 2, "avg_duration_ms": 4000}
        }
        mock_repo.get_trace_statistics.return_value = mock_stats
        
        # Execute
        result = await trace_service.get_trace_statistics(tenant_id)
        
        # Verify
        assert result == mock_stats
        mock_repo.get_trace_statistics.assert_called_once_with(tenant_id, None, None)
    
    def test_calculate_prompt_hash(self, trace_service):
        """Test prompt hash calculation."""
        # Execute
        prompt = "# IDENTITY\nYou are a Triage Agent\n\n# MISSION\nDetermine next action"
        hash1 = trace_service.calculate_prompt_hash(prompt)
        hash2 = trace_service.calculate_prompt_hash(prompt)
        hash3 = trace_service.calculate_prompt_hash("Different prompt")
        
        # Verify
        assert hash1 == hash2  # Same prompt should produce same hash
        assert hash1 != hash3  # Different prompt should produce different hash
        assert len(hash1) == 16  # Should be truncated to 16 characters
        assert all(c in '0123456789abcdef' for c in hash1)  # Should be hex characters
    
    @pytest.mark.asyncio
    async def test_context_variables_extraction(
        self, trace_service, mock_repo, sample_role_config
    ):
        """Test context variables extraction for different trace types."""
        # Test triage context extraction
        triage_input = {
            "user_message": "Hello",
            "available_agents": [{"slug": "agent1"}],
            "policies": "default",
            "active_run": None
        }
        
        mock_trace = Mock(spec=SystemLLMTrace)
        mock_repo.create.return_value = mock_trace
        
        await trace_service.create_trace(
            trace_type=SystemLLMTraceType.TRIAGE,
            role_config=sample_role_config,
            structured_input=triage_input,
            messages_sent=[],
            raw_response="",
            parsed_response=None,
            validation_status="success",
            duration_ms=100,
            model="test",
            temperature=0.0,
            max_tokens=100,
            tenant_id=uuid.uuid4()
        )
        
        # Verify context variables were extracted correctly
        call_args = mock_repo.create.call_args[0][0]
        context_vars = call_args.context_variables
        assert context_vars["available_agents"] == [{"slug": "agent1"}]
        assert context_vars["policies"] == "default"
        assert context_vars["active_run"] is None
        
        # Test planner context extraction
        planner_input = {
            "goal": "Create plan",
            "available_agents": [{"slug": "agent1"}],
            "available_tools": [{"tool_slug": "tool1"}],
            "policies": "strict"
        }
        
        await trace_service.create_trace(
            trace_type=SystemLLMTraceType.PLANNER,
            role_config=sample_role_config,
            structured_input=planner_input,
            messages_sent=[],
            raw_response="",
            parsed_response=None,
            validation_status="success",
            duration_ms=100,
            model="test",
            temperature=0.0,
            max_tokens=100,
            tenant_id=uuid.uuid4()
        )
        
        call_args = mock_repo.create.call_args[0][0]
        context_vars = call_args.context_variables
        assert context_vars["available_agents"] == [{"slug": "agent1"}]
        assert context_vars["available_operations"] == [{"tool_slug": "tool1"}]
        assert context_vars["policies"] == "strict"
