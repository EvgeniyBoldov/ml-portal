"""
Unit tests for SystemLLMExecutor with mocked LLM client.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from app.services.system_llm_executor import SystemLLMExecutor, SystemLLMExecutorError
from app.models.system_llm_role import SystemLLMRoleType
from app.schemas.system_llm_roles import TriageInput, PlannerInput, SummaryInput


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = AsyncMock()
    # Return string content, not dict
    client.chat.return_value = '{"type": "final", "answer": "Hello!"}'
    return client


@pytest.fixture
def mock_role_service():
    """Mock SystemLLMRoleService."""
    service = AsyncMock()
    service.get_role_config.return_value = {
        "id": str(uuid.uuid4()),
        "role_type": "triage",
        "prompt": "# IDENTITY\nYou are a Triage Agent",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.0,
        "max_tokens": 1000,
        "timeout_s": 10,
        "max_retries": 2,
        "retry_backoff": "linear"
    }
    return service


@pytest.fixture
def mock_trace_service():
    """Mock SystemLLMTraceService."""
    service = AsyncMock()
    service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
    return service


@pytest.fixture
def executor(mock_session, mock_llm_client, mock_role_service, mock_trace_service):
    """SystemLLMExecutor with mocked dependencies."""
    executor = SystemLLMExecutor(mock_session, mock_llm_client)
    executor.role_service = mock_role_service
    executor.trace_service = mock_trace_service
    return executor


@pytest.fixture
def sample_triage_input():
    """Sample TriageInput."""
    return TriageInput(
        user_message="Create business plan",
        conversation_summary="User wants help with business planning",
        session_state={"status": "active"},
        available_agents=[{"slug": "business-planner"}],
        policies="default",
        active_run=None
    )


@pytest.fixture
def sample_planner_input():
    """Sample PlannerInput."""
    return PlannerInput(
        goal="Create business plan",
        conversation_summary="User wants help with business planning",
        session_state={"status": "active"},
        available_agents=[{"slug": "business-planner"}],
        available_tools=[{"tool_slug": "rag.search", "ops": ["run"]}],
        policies="default"
    )


@pytest.fixture
def sample_summary_input():
    """Sample SummaryInput."""
    return SummaryInput(
        previous_summary="Previous summary",
        recent_messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ],
        session_state={"status": "active"}
    )


class TestSystemLLMExecutor:
    """Test cases for SystemLLMExecutor."""
    
    @pytest.mark.asyncio
    async def test_execute_triage_success(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test successful triage execution."""
        # Setup
        mock_llm_client.chat.return_value = '{"type": "plan", "confidence": 0.9}'
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result, trace_id = await executor.execute_triage(
            sample_triage_input,
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4()
        )
        
        # Verify
        assert result.type == "plan"
        assert result.confidence == 0.9
        assert trace_id is not None
        
        # Verify role service was called
        mock_role_service.get_role_config.assert_called_once_with(SystemLLMRoleType.TRIAGE)
        
        # Verify LLM was called
        mock_llm_client.chat.assert_called_once()
        call_args = mock_llm_client.chat.call_args
        assert "messages" in call_args[1]
        assert "model" in call_args[1]
        assert "params" in call_args[1]
        
        # Verify trace was created
        mock_trace_service.create_trace_from_execution.assert_called_once()
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["trace_type"] == SystemLLMRoleType.TRIAGE
        assert trace_call_args[1]["validation_status"] == "success"
    
    @pytest.mark.asyncio
    async def test_execute_planner_success(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_planner_input
    ):
        """Test successful planner execution."""
        # Setup
        mock_role_service.get_role_config.return_value = {
            **mock_role_service.get_role_config.return_value,
            "role_type": "planner"
        }
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": '{"steps": [{"step_id": "1", "kind": "tool"}]}'}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result, trace_id = await executor.execute_planner(
            sample_planner_input,
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            agent_run_id=uuid.uuid4()
        )
        
        # Verify
        assert len(result.steps) == 1
        assert result.steps[0].step_id == "1"
        assert result.steps[0].kind == "tool"
        assert trace_id is not None
        
        # Verify role service was called
        mock_role_service.get_role_config.assert_called_once_with(SystemLLMRoleType.PLANNER)
        
        # Verify trace was created
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["trace_type"] == SystemLLMRoleType.PLANNER
        assert trace_call_args[1]["validation_status"] == "success"
    
    @pytest.mark.asyncio
    async def test_execute_summary_success(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_summary_input
    ):
        """Test successful summary execution."""
        # Setup
        mock_role_service.get_role_config.return_value = {
            **mock_role_service.get_role_config.return_value,
            "role_type": "summary"
        }
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": "Summary: User asked for help with business planning"}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result, trace_id = await executor.execute_summary(
            sample_summary_input,
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4()
        )
        
        # Verify
        assert result == "Summary: User asked for help with business planning"
        assert trace_id is not None
        
        # Verify role service was called
        mock_role_service.get_role_config.assert_called_once_with(SystemLLMRoleType.SUMMARY)
        
        # Verify trace was created
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["trace_type"] == SystemLLMRoleType.SUMMARY
        assert trace_call_args[1]["validation_status"] == "success"
        assert trace_call_args[1]["result_type"] == "text"
    
    @pytest.mark.asyncio
    async def test_execute_triage_with_fallback(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test triage execution with smart fallback."""
        # Setup
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": '{"type": "final", "response": "I will help"}'}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result, trace_id = await executor.execute_triage(sample_triage_input)
        
        # Verify fallback was applied (type "final" mapped to "plan" for triage)
        assert result.type == "plan"  # Should be mapped from "final"
        assert trace_id is not None
        
        # Verify trace shows fallback applied
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["validation_status"] == "fallback_applied"
        assert trace_call_args[1]["fallback_applied"] is True
    
    @pytest.mark.asyncio
    async def test_execute_planner_with_fallback(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_planner_input
    ):
        """Test planner execution with fallback method."""
        # Setup
        mock_role_service.get_role_config.return_value = {
            **mock_role_service.get_role_config.return_value,
            "role_type": "planner"
        }
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": '{"steps": [{"step_id": "1", "kind": "tool"}]'}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result = await executor.execute_planner_with_fallback(
            sample_planner_input,
            chat_id=uuid.uuid4(),
            tenant_id=uuid.uuid4()
        )
        
        # Verify
        assert result.tool.intent.tool_slug == "1"  # Converted from step_id
        assert result.tool.intent.op == "tool"  # Converted from kind
        assert trace_id is not None
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_failure(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test execution failure after retries."""
        # Setup
        mock_llm_client.chat.side_effect = Exception("LLM error")
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute and verify exception
        with pytest.raises(SystemLLMExecutorError) as exc_info:
            await executor.execute_triage(sample_triage_input)
        
        assert "Failed to execute triage after 3 attempts" in str(exc_info.value)
        
        # Verify LLM was called 3 times (1 initial + 2 retries)
        assert mock_llm_client.chat.call_count == 3
        
        # Verify trace was created for each failed attempt
        assert mock_trace_service.create_trace_from_execution.call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_with_json_decode_error(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test execution with JSON decode error."""
        # Setup
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": "not a json response"}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute and verify exception
        with pytest.raises(SystemLLMExecutorError) as exc_info:
            await executor.execute_triage(sample_triage_input)
        
        assert "Invalid JSON response" in str(exc_info.value)
        
        # Verify trace was created with failed status
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["validation_status"] == "failed"
        assert "Invalid JSON response" in trace_call_args[1]["validation_error"]
    
    @pytest.mark.asyncio
    async def test_execute_with_markdown_json(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test execution with JSON wrapped in markdown."""
        # Setup
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": "Here is the response:\n```json\n{\"type\": \"plan\"}\n```"}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute
        result, trace_id = await executor.execute_triage(sample_triage_input)
        
        # Verify JSON was extracted correctly
        assert result.type == "plan"
        assert trace_id is not None
        
        # Verify trace was created successfully
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["validation_status"] == "success"
    
    @pytest.mark.asyncio
    async def test_backward_compatibility(
        self, executor, mock_llm_client, mock_role_service, mock_trace_service,
        sample_triage_input
    ):
        """Test that executor still works without context parameters (backward compatibility)."""
        # Setup
        mock_llm_client.chat.return_value = {
            "choices": [{"message": {"content": '{"type": "plan", "confidence": 0.9}'}}]
        }
        mock_trace_service.create_trace_from_execution.return_value = Mock(id=uuid.uuid4())
        
        # Execute without context parameters
        result, trace_id = await executor.execute_triage(sample_triage_input)
        
        # Verify it still works
        assert result.type == "plan"
        assert trace_id is not None
        
        # Verify trace was created with None context
        trace_call_args = mock_trace_service.create_trace_from_execution.call_args
        assert trace_call_args[1]["chat_id"] is None
        assert trace_call_args[1]["tenant_id"] is None
        assert trace_call_args[1]["user_id"] is None
    
    def test_extract_result_summary(self, executor):
        """Test result summary extraction."""
        # Test final response
        result = {"type": "final", "answer": "This is a long answer that should be truncated"}
        summary = executor._extract_result_summary(result)
        assert summary == "This is a long answer that should be trunc..."
        
        # Test plan response
        result = {"type": "plan", "steps": [{"step_id": "1"}, {"step_id": "2"}]}
        summary = executor._extract_result_summary(result)
        assert summary == "Plan with 2 steps"
        
        # Test agent response
        result = {"type": "agent", "agent_slug": "business-planner"}
        summary = executor._extract_result_summary(result)
        assert summary == "Agent: business-planner"
        
        # Test ask_user response
        result = {"type": "ask_user", "question": "What would you like to know?"}
        summary = executor._extract_result_summary(result)
        assert summary == "What would you like to know?"
        
        # Test unknown response
        result = {"type": "unknown"}
        summary = executor._extract_result_summary(result)
        assert summary == "Response type: unknown"
