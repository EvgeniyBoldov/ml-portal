"""
Regression тесты для рефакторинга Agent Runtime
Сравнивают поведение нового runtime с ожидаемым от legacy
"""
import pytest
import asyncio
import time
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from app.agents.runtime import AgentRuntime
from app.agents.context import ToolContext


class TestRuntimeRegression:
    """Regression тесты для runtime"""
    
    @pytest.fixture
    async def mock_llm_client(self):
        """Mock LLM client с предсказуемыми ответами"""
        client = AsyncMock()
        
        # Mock responses для разных сценариев
        responses = {
            "simple": '{"content": "Hello! How can I help you today?", "tool_calls": []}',
            "tool_call": '{"content": null, "tool_calls": [{"id": "call_1", "tool": "rag.search", "arguments": {"query": "test"}}]}',
            "error": '{"error": "Mock error"}'
        }
        
        def mock_chat(messages, **kwargs):
            # Определяем ответ на основе последнего сообщения
            last_msg = messages[-1] if messages else {}
            content = last_msg.get("content", "").lower()
            
            if "search" in content or "find" in content:
                return responses["tool_call"]
            elif "error" in content:
                return responses["error"]
            else:
                return responses["simple"]
        
        client.chat = mock_chat
        
        # Mock streaming
        async def mock_stream(messages, **kwargs):
            last_msg = messages[-1] if messages else {}
            content = last_msg.get("content", "").lower()
            
            if "search" in content or "find" in content:
                yield "Searching for information..."
            elif "error" in content:
                yield "An error occurred"
            else:
                yield "Hello! How can I help you today?"
        
        client.chat_stream = mock_stream
        return client
    
    @pytest.fixture
    async def runtime(self, mock_llm_client):
        """AgentRuntime с mock LLM"""
        return AgentRuntime(llm_client=mock_llm_client)
    
    @pytest.fixture
    async def tool_context(self):
        """ToolContext для тестов"""
        return ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4())
        )
    
    async def test_simple_chat_regression(
        self,
        runtime,
        tool_context
    ):
        """Regression тест для простого чата без tools"""
        
        # Mock execution request для простого чата
        execution_request = self._create_simple_execution_request()
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock final response
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Выполняем runtime
            events = []
            async for event in runtime.run_with_planner(
                exec_request=execution_request,
                messages=[{"role": "user", "content": "Hello"}],
                ctx=tool_context,
                enable_logging=False
            ):
                events.append(event)
                if event.type.value == "final":
                    break
            
            # Проверяем regression
            assert len(events) > 0, "Should generate events"
            assert any(e.type.value == "final" for e in events), "Should have final event"
            assert any(e.type.value == "planner_loop_started" for e in events), "Should start planner loop"
            
            # Проверяем что нет legacy событий
            assert not any(e.type.value == "legacy" for e in events), "Should not have legacy events"
    
    async def test_tool_execution_regression(
        self,
        runtime,
        tool_context
    ):
        """Regression тест для выполнения tools"""
        
        execution_request = self._create_tool_execution_request()
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock tool action
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            mock_next_action = NextAction(
                action_type=ActionType.TOOL,
                tool=ToolActionPayload(intent=MagicMock()),
                meta=ActionMeta(why="Search for information")
            )
            mock_next_action.tool.intent.tool_slug = "rag.search"
            mock_next_action.tool.intent.op = "run"
            mock_next_action.tool.input = {"query": "test query"}
            
            mock_executor.execute_planner_with_fallback.return_value = mock_next_action
            
            with patch('app.agents.runtime.ToolRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                # Mock tool handler
                mock_tool_handler = AsyncMock()
                mock_tool_handler.slug = "rag.search"
                mock_router.select.return_value = mock_tool_handler
                
                from app.agents.context import ToolResult
                mock_tool_handler.execute.return_value = ToolResult(
                    success=True,
                    data={"results": ["test result"]},
                    metadata={}
                )
                
                # Выполняем runtime
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "Search for test"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    
                    # Останавливаем после tool execution
                    if event.type.value == "tool_result":
                        break
                
                # Проверяем regression
                assert len(events) > 0, "Should generate events"
                assert any(e.type.value == "tool_call" for e in events), "Should have tool call event"
                assert any(e.type.value == "tool_result" for e in events), "Should have tool result event"
                assert any(e.type.value == "planner_action" for e in events), "Should have planner action event"
    
    async def test_event_streaming_regression(
        self,
        runtime,
        tool_context
    ):
        """Regression тест для стриминга событий"""
        
        execution_request = self._create_simple_execution_request()
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock streaming response
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Собираем события в реальном времени
            events_received = []
            event_types = []
            
            async for event in runtime.run_with_planner(
                exec_request=execution_request,
                messages=[{"role": "user", "content": "Test streaming"}],
                ctx=tool_context,
                enable_logging=False
            ):
                events_received.append(event)
                event_types.append(event.type.value)
                
                if event.type.value == "final":
                    break
            
            # Проверяем что события приходят в правильном порядке
            expected_flow = ["planner_loop_started", "thinking", "planner_action", "final"]
            
            # Проверяем наличие ключевых событий
            for expected_type in expected_flow:
                assert expected_type in event_types, f"Missing event type: {expected_type}"
            
            # Проверяем что события имеют правильную структуру
            for event in events_received:
                assert hasattr(event, 'type'), "Event should have type"
                assert hasattr(event, 'data'), "Event should have data"
                assert event.type.value in [
                    "status", "thinking", "planner_action", "policy_decision",
                    "tool_call", "tool_result", "final", "error", "delta"
                ], f"Invalid event type: {event.type.value}"
    
    async def test_error_handling_regression(
        self,
        runtime,
        tool_context
    ):
        """Regression тест для обработки ошибок"""
        
        execution_request = self._create_simple_execution_request()
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock planner error
            mock_executor.execute_planner_with_fallback.side_effect = Exception("Planner error")
            
            # Выполняем и проверяем обработку ошибок
            events = []
            error_caught = False
            
            try:
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "Cause error"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
            except Exception:
                error_caught = True
            
            # Should handle error gracefully
            assert not error_caught, "Should not raise exception"
            assert len(events) > 0, "Should generate events even with error"
            
            # Should have error event
            error_events = [e for e in events if e.type.value == "error"]
            assert len(error_events) > 0, "Should have error event"
    
    async def test_conversation_summary_regression(
        self,
        runtime,
        tool_context
    ):
        """Regression тест для conversation summaries"""
        
        execution_request = self._create_simple_execution_request()
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Capture planner inputs
            planner_inputs = []
            
            def capture_planner_input(planner_input):
                planner_inputs.append(planner_input)
                from app.agents.contracts import NextAction, ActionType
                return NextAction(
                    action_type=ActionType.FINAL,
                    final=MagicMock(),
                    meta=MagicMock()
                )
            
            mock_executor.execute_planner_with_fallback.side_effect = capture_planner_input
            
            # Выполняем с историей сообщений
            messages = [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Response 1"},
                {"role": "user", "content": "Second"},
                {"role": "assistant", "content": "Response 2"},
                {"role": "user", "content": "Current"}
            ]
            
            async for event in runtime.run_with_planner(
                exec_request=execution_request,
                messages=messages,
                ctx=tool_context,
                enable_logging=False
            ):
                if event.type.value == "final":
                    break
            
            # Проверяем что conversation summary был извлечен
            assert len(planner_inputs) > 0, "Should have planner input"
            
            planner_input = planner_inputs[0]
            assert hasattr(planner_input, 'conversation_summary'), "Should have conversation_summary"
            assert planner_input.conversation_summary is not None, "Conversation summary should not be None"
            
            # Проверяем что summary содержит ключевую информацию
            summary = planner_input.conversation_summary
            assert "First" in summary, "Summary should contain first message"
            assert "Second" in summary, "Summary should contain second message"
    
    def _create_simple_execution_request(self):
        """Создать простой ExecutionRequest"""
        from app.agents.router import ExecutionRequest, ExecutionMode, AvailableActions, EffectivePermissions
        
        request = MagicMock(spec=ExecutionRequest)
        request.agent = MagicMock()
        request.agent.slug = "test-agent"
        request.agent_version = MagicMock()
        request.mode = ExecutionMode.FULL
        request.request_text = "Test request"
        request.prompt = "Test prompt"
        
        # Пустые available actions
        actions = MagicMock(spec=AvailableActions)
        actions.tools = []
        actions.agents = []
        request.available_actions = actions
        
        # Пустые permissions
        permissions = MagicMock(spec=EffectivePermissions)
        permissions.allowed_tools = set()
        permissions.denied_reasons = {}
        request.effective_permissions = permissions
        
        # Default policy
        request.policy_data = {"execution": {"max_steps": 5}}
        request.limit_data = {"limits": {"max_tool_calls": 10}}
        
        return request
    
    def _create_tool_execution_request(self):
        """Создать ExecutionRequest для tool execution"""
        from app.agents.router import ExecutionRequest, ExecutionMode, AvailableActions, AvailableTool, EffectivePermissions
        
        request = MagicMock(spec=ExecutionRequest)
        request.agent = MagicMock()
        request.agent.slug = "test-agent"
        request.agent_version = MagicMock()
        request.mode = ExecutionMode.FULL
        request.request_text = "Test request"
        request.prompt = "Test prompt"
        
        # Tool в available actions
        tool = MagicMock(spec=AvailableTool)
        tool.tool_slug = "rag.search"
        tool.op = "run"
        tool.side_effects = False
        tool.risk_level = "low"
        tool.idempotent = True
        
        actions = MagicMock(spec=AvailableActions)
        actions.tools = [tool]
        actions.agents = []
        request.available_actions = actions
        
        # Permissions для tool
        permissions = MagicMock(spec=EffectivePermissions)
        permissions.allowed_tools = {"rag.search"}
        permissions.denied_reasons = {}
        request.effective_permissions = permissions
        
        # Policy
        request.policy_data = {"execution": {"max_steps": 5}}
        request.limit_data = {"limits": {"max_tool_calls": 10}}
        
        return request


class TestLegacyBehaviorRemoval:
    """Тесты удаления legacy поведения"""
    
    async def test_no_legacy_run_method(self):
        """Убедиться что legacy run() метод удален"""
        runtime = AgentRuntime(llm_client=AsyncMock())
        
        assert not hasattr(runtime, 'run'), "Legacy run() method should be removed"
        assert hasattr(runtime, 'run_with_planner'), "Should have run_with_planner method"
    
    async def test_no_legacy_run_with_request_method(self):
        """Убедиться что legacy run_with_request() метод удален"""
        runtime = AgentRuntime(llm_client=AsyncMock())
        
        assert not hasattr(runtime, 'run_with_request'), "Legacy run_with_request() method should be removed"
        assert hasattr(runtime, 'run_with_planner'), "Should have run_with_planner method"
    
    async def test_no_agent_profile_import(self):
        """Убедиться что AgentProfile удален"""
        try:
            from app.agents.runtime import AgentProfile
            assert False, "AgentProfile should be removed"
        except ImportError:
            pass  # Expected
    
    async def test_no_run_context_import(self):
        """Убедиться что RunContext удален"""
        try:
            from app.agents.context import RunContext
            assert False, "RunContext should be removed"
        except ImportError:
            pass  # Expected
    
    async def test_no_run_step_import(self):
        """Убедиться что RunStep удален"""
        try:
            from app.agents.context import RunStep
            assert False, "RunStep should be removed"
        except ImportError:
            pass  # Expected
    
    async def test_sandbox_uses_new_runtime(self):
        """Проверить что sandbox использует новый runtime"""
        import os
        
        sandbox_path = os.path.join(
            os.path.dirname(__file__),
            '../../app/api/v1/routers/sandbox.py'
        )
        
        with open(sandbox_path, 'r') as f:
            content = f.read()
        
        assert 'run_with_planner' in content, "Sandbox should use run_with_planner"
        assert 'run_with_request' not in content, "Sandbox should not use run_with_request"
        assert 'AgentProfile' not in content, "Sandbox should not use AgentProfile"
    
    async def test_chat_stream_service_uses_new_runtime(self):
        """Проверить что chat_stream_service использует новый runtime"""
        import os
        
        service_path = os.path.join(
            os.path.dirname(__file__),
            '../../app/services/chat_stream_service.py'
        )
        
        with open(service_path, 'r') as f:
            content = f.read()
        
        assert 'run_with_planner' in content, "ChatStreamService should use run_with_planner"
        assert 'run_with_request' not in content, "ChatStreamService should not use run_with_request"
        assert 'AgentProfile' not in content, "ChatStreamService should not use AgentProfile"


class TestRuntimeCompatibility:
    """Тесты совместимости нового runtime"""
    
    async def test_event_format_compatibility(self):
        """Проверить что формат событий совместим"""
        from app.agents.runtime import RuntimeEvent, RuntimeEventType
        
        # Все типы событий должны быть доступны
        expected_types = [
            "status", "thinking", "tool_call", "tool_result", 
            "delta", "final", "error", "planner_action", "policy_decision"
        ]
        
        for event_type in expected_types:
            assert hasattr(RuntimeEventType, event_type.upper()), f"Missing event type: {event_type}"
        
        # Проверяем что события создаются правильно
        status_event = RuntimeEvent.status("test_status")
        assert status_event.type == RuntimeEventType.STATUS
        assert status_event.data == {"status": "test_status"}
        
        error_event = RuntimeEvent.error("Test error", recoverable=True)
        assert error_event.type == RuntimeEventType.ERROR
        assert error_event.data["error"] == "Test error"
        assert error_event.data["recoverable"] is True
    
    async def test_tool_context_compatibility(self):
        """Проверить что ToolContext совместим"""
        from app.agents.context import ToolContext
        
        # Создаем ToolContext
        ctx = ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4()),
            extra={"test": "value"}
        )
        
        # Проверяем что все атрибуты доступны
        assert hasattr(ctx, 'tenant_id')
        assert hasattr(ctx, 'user_id')
        assert hasattr(ctx, 'chat_id')
        assert hasattr(ctx, 'request_id')
        assert hasattr(ctx, 'extra')
        
        # Проверяем значения
        assert ctx.tenant_id is not None
        assert ctx.user_id is not None
        assert ctx.chat_id is not None
        assert ctx.request_id is not None
        assert ctx.extra["test"] == "value"
    
    async def test_execution_request_compatibility(self):
        """Проверить что ExecutionRequest совместим"""
        from app.agents.router import ExecutionRequest, ExecutionMode
        
        # Mock ExecutionRequest
        request = MagicMock(spec=ExecutionRequest)
        request.agent = MagicMock()
        request.agent.slug = "test-agent"
        request.mode = ExecutionMode.FULL
        request.request_text = "Test"
        
        # Проверяем что все необходимые поля доступны
        assert hasattr(request, 'agent')
        assert hasattr(request, 'mode')
        assert hasattr(request, 'request_text')
        assert hasattr(request, 'available_actions')
        assert hasattr(request, 'effective_permissions')
        assert hasattr(request, 'policy_data')
        assert hasattr(request, 'limit_data')
        
        # Проверяем значения
        assert request.agent.slug == "test-agent"
        assert request.mode == ExecutionMode.FULL
        assert request.request_text == "Test"
