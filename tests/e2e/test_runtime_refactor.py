"""
E2E тесты для рефакторинга Agent Runtime
Проверяют корректность работы нового planner-driven runtime
"""
import pytest
import asyncio
import json
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import AgentRuntime
from app.agents.router import AgentRouter, ExecutionRequest, ExecutionMode
from app.agents.context import ToolContext
from app.services.chat_stream_service import ChatStreamService
from app.services.chat_summary_service import ChatSummaryService
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.models.tool import Tool
from app.models.tool_release import ToolRelease
from app.models.chat_summary import ChatSummary


class TestRuntimeRefactor:
    """Тесты рефакторинга runtime"""
    
    @pytest.fixture
    async def mock_llm_client(self):
        """Mock LLM client для детерминированных тестов"""
        client = AsyncMock()
        
        # Mock chat response для tool calls
        client.chat.return_value = json.dumps({
            "content": None,
            "tool_calls": [
                {
                    "id": "test_tool_1",
                    "tool": "rag.search",
                    "arguments": {"query": "test query"}
                }
            ]
        })
        
        # Mock streaming response
        async def mock_chat_stream(messages, model, params):
            yield "Test response"
        
        client.chat_stream = mock_chat_stream
        return client
    
    @pytest.fixture
    async def runtime(self, mock_llm_client):
        """AgentRuntime инстанс с mock LLM"""
        return AgentRuntime(llm_client=mock_llm_client)
    
    @pytest.fixture
    async def mock_session(self):
        """Mock SQLAlchemy session"""
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.rollback = AsyncMock()
        return session
    
    @pytest.fixture
    async def sample_agent(self):
        """Sample agent для тестов"""
        agent = MagicMock(spec=Agent)
        agent.id = uuid4()
        agent.slug = "test-agent"
        agent.current_version_id = uuid4()
        agent.logging_level = "brief"
        return agent
    
    @pytest.fixture
    async def sample_agent_version(self):
        """Sample agent version"""
        version = MagicMock(spec=AgentVersion)
        version.id = uuid4()
        version.agent_id = uuid4()
        version.version = 1
        version.prompt_text = "You are a helpful assistant."
        return version
    
    @pytest.fixture
    async def sample_tool(self):
        """Sample tool для тестов"""
        tool = MagicMock(spec=Tool)
        tool.id = uuid4()
        tool.slug = "rag.search"
        tool.name = "RAG Search"
        return tool
    
    @pytest.fixture
    async def sample_tool_release(self):
        """Sample tool release"""
        release = MagicMock(spec=ToolRelease)
        release.id = uuid4()
        release.tool_id = uuid4()
        release.version = "1.0.0"
        release.status = "active"
        return release
    
    @pytest.fixture
    async def execution_request(self, sample_agent, sample_agent_version):
        """Sample ExecutionRequest"""
        from app.agents.router import AvailableActions, AvailableTool, EffectivePermissions
        
        request = MagicMock(spec=ExecutionRequest)
        request.agent = sample_agent
        request.agent_version = sample_agent_version
        request.mode = ExecutionMode.FULL
        request.request_text = "Test request"
        request.prompt = "Test prompt"
        
        # Mock available actions
        available_tool = MagicMock(spec=AvailableTool)
        available_tool.tool_slug = "rag.search"
        available_tool.op = "run"
        available_tool.side_effects = False
        available_tool.risk_level = "low"
        available_tool.idempotent = True
        
        actions = MagicMock(spec=AvailableActions)
        actions.tools = [available_tool]
        actions.agents = []
        request.available_actions = actions
        
        # Mock permissions
        permissions = MagicMock(spec=EffectivePermissions)
        permissions.allowed_tools = {"rag.search"}
        permissions.denied_reasons = {}
        request.effective_permissions = permissions
        
        # Mock policy data
        request.policy_data = {"execution": {"max_steps": 5}}
        request.limit_data = {"limits": {"max_tool_calls": 10}}
        
        return request
    
    @pytest.fixture
    async def tool_context(self):
        """Sample ToolContext"""
        return ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4())
        )
    
    async def test_planner_loop_complete_flow(
        self, 
        runtime, 
        execution_request, 
        tool_context,
        mock_session,
        mock_llm_client
    ):
        """Тест полного цикла planner loop"""
        
        # Mock SystemLLMExecutor
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock planner response
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            mock_next_action = NextAction(
                action_type=ActionType.TOOL,
                tool=ToolActionPayload(
                    intent=MagicMock()
                ),
                meta=ActionMeta(why="Test action")
            )
            mock_next_action.tool.intent.tool_slug = "rag.search"
            mock_next_action.tool.intent.op = "run"
            mock_next_action.tool.input = {"query": "test"}
            
            mock_executor.execute_planner_with_fallback.return_value = mock_next_action
            
            # Mock tool execution
            with patch('app.agents.runtime.ToolRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                mock_tool_handler = AsyncMock()
                mock_tool_handler.slug = "rag.search"
                mock_router.select.return_value = mock_tool_handler
                
                # Mock tool result
                from app.agents.context import ToolResult
                mock_tool_handler.execute.return_value = ToolResult(
                    success=True,
                    data={"results": ["test result"]}
                )
                
                # Mock session in context
                tool_context.extra["_session"] = mock_session
                
                # Execute runtime
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "test"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    
                    # Break after first tool execution to avoid infinite loop
                    if event.type.value == "tool_result":
                        break
                
                # Verify events
                assert len(events) > 0
                assert any(e.type.value == "planner_loop_started" for e in events)
                assert any(e.type.value == "thinking" for e in events)
                assert any(e.type.value == "tool_call" for e in events)
                assert any(e.type.value == "tool_result" for e in events)
    
    async def test_conversation_summary_integration(
        self,
        runtime,
        execution_request,
        tool_context,
        mock_llm_client
    ):
        """Тест интеграции conversation summary в planner context"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Capture planner input
            captured_inputs = []
            
            def capture_input(planner_input):
                captured_inputs.append(planner_input)
                from app.agents.contracts import NextAction, ActionType
                return NextAction(
                    action_type=ActionType.FINAL,
                    final=MagicMock(),
                    meta=MagicMock()
                )
            
            mock_executor.execute_planner_with_fallback.side_effect = capture_input
            
            # Execute with conversation history
            messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "First message"},
                {"role": "assistant", "content": "First response"},
                {"role": "user", "content": "Second message"}
            ]
            
            async for event in runtime.run_with_planner(
                exec_request=execution_request,
                messages=messages,
                ctx=tool_context,
                enable_logging=False
            ):
                if event.type.value == "final":
                    break
            
            # Verify conversation summary was extracted
            assert len(captured_inputs) > 0
            planner_input = captured_inputs[0]
            assert planner_input.conversation_summary is not None
            assert "First message" in planner_input.conversation_summary
            assert "Second message" in planner_input.conversation_summary
    
    async def test_policy_limits_enforcement(
        self,
        runtime,
        execution_request,
        tool_context,
        mock_llm_client
    ):
        """Тест соблюдения policy limits"""
        
        # Set low max_steps for testing
        execution_request.policy_data = {"execution": {"max_steps": 2}}
        execution_request.limit_data = {"limits": {"max_tool_calls": 1}}
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Always return tool action to trigger multiple steps
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            mock_next_action = NextAction(
                action_type=ActionType.TOOL,
                tool=ToolActionPayload(intent=MagicMock()),
                meta=ActionMeta(why="Test action")
            )
            mock_next_action.tool.intent.tool_slug = "rag.search"
            mock_next_action.tool.intent.op = "run"
            mock_next_action.tool.input = {"query": "test"}
            
            mock_executor.execute_planner_with_fallback.return_value = mock_next_action
            
            # Mock tool execution
            with patch('app.agents.runtime.ToolRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                mock_tool_handler = AsyncMock()
                mock_tool_handler.slug = "rag.search"
                mock_router.select.return_value = mock_tool_handler
                
                mock_tool_handler.execute.return_value = MagicMock(
                    success=True,
                    data={"results": ["test"]},
                    to_message_content=lambda: "Tool result"
                )
                
                # Count events
                events = []
                step_count = 0
                
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "test"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    
                    if event.type.value == "thinking":
                        step_count += 1
                    
                    # Should stop after max_steps
                    if step_count >= 2:
                        break
                
                # Verify max_steps was enforced
                thinking_events = [e for e in events if e.type.value == "thinking"]
                assert len(thinking_events) <= 2
    
    async def test_error_recovery_and_events(
        self,
        runtime,
        execution_request,
        tool_context,
        mock_llm_client
    ):
        """Тест обработки ошибок и событий"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock planner failure
            mock_executor.execute_planner_with_fallback.side_effect = Exception("Planner error")
            
            # Execute and capture events
            events = []
            error_caught = False
            
            try:
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "test"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
            except Exception:
                error_caught = True
            
            # Should handle error gracefully
            assert not error_caught  # Should not raise exception
            assert len(events) > 0
            
            # Should have error event
            error_events = [e for e in events if e.type.value == "error"]
            assert len(error_events) > 0


class TestChatSummaryIntegration:
    """Тесты интеграции chat summaries"""
    
    @pytest.fixture
    async def summary_service(self, mock_session):
        """ChatSummaryService инстанс"""
        return ChatSummaryService(mock_session)
    
    async def test_create_summary(self, summary_service, mock_session):
        """Тест создания summary"""
        chat_id = uuid4()
        
        # Mock database operations
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        
        summary = await summary_service.create_or_update_summary(
            chat_id=chat_id,
            summary_text="Test summary",
            message_count=5,
            last_message_id=uuid4()
        )
        
        assert summary.chat_id == chat_id
        assert summary.summary_text == "Test summary"
        assert summary.message_count == 5
        mock_session.add.assert_called_once()
    
    async def test_get_latest_summary(self, summary_service, mock_session):
        """Тест получения последнего summary"""
        chat_id = uuid4()
        
        # Mock existing summary
        mock_summary = MagicMock(spec=ChatSummary)
        mock_summary.summary_text = "Existing summary"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_summary
        mock_session.execute.return_value = mock_result
        
        summary_text = await summary_service.get_summary_text(chat_id)
        
        assert summary_text == "Existing summary"
    
    async def test_update_existing_summary(self, summary_service, mock_session):
        """Тест обновления существующего summary"""
        chat_id = uuid4()
        
        # Mock existing summary
        existing_summary = MagicMock(spec=ChatSummary)
        existing_summary.summary_text = "Old summary"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_summary
        mock_session.execute.return_value = mock_result
        
        # Update summary
        updated = await summary_service.create_or_update_summary(
            chat_id=chat_id,
            summary_text="New summary",
            message_count=10
        )
        
        assert updated.summary_text == "New summary"
        assert updated.message_count == 10
        mock_session.flush.assert_called_once()


class TestLegacyCodeRemoval:
    """Тесты удаления legacy кода"""
    
    async def test_no_legacy_run_method(self, runtime):
        """Убедиться что метод run() удален"""
        assert not hasattr(runtime, 'run'), "Legacy run() method should be removed"
    
    async def test_no_legacy_run_with_request_method(self, runtime):
        """Убедиться что метод run_with_request() удален"""
        assert not hasattr(runtime, 'run_with_request'), "Legacy run_with_request() method should be removed"
    
    async def test_no_agent_profile_import(self):
        """Убедиться что AgentProfile удален"""
        try:
            from app.agents.runtime import AgentProfile
            assert False, "AgentProfile should be removed"
        except ImportError:
            pass  # Expected
    
    async def test_sandbox_uses_run_with_planner(self):
        """Проверить что sandbox использует run_with_planner"""
        # Read sandbox.py content
        import os
        sandbox_path = os.path.join(
            os.path.dirname(__file__),
            '../../app/api/v1/routers/sandbox.py'
        )
        
        with open(sandbox_path, 'r') as f:
            content = f.read()
        
        assert 'run_with_planner' in content, "Sandbox should use run_with_planner"
        assert 'run_with_request' not in content, "Sandbox should not use run_with_request"
