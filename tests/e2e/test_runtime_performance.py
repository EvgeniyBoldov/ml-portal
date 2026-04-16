"""
Performance тесты для рефакторинга Agent Runtime
Проверяют что производительность не ухудшилась после рефакторинга
"""
import pytest
import asyncio
import time
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from app.agents.runtime import AgentRuntime
from app.agents.router import ExecutionRequest, ExecutionMode
from app.agents.context import ToolContext


class TestRuntimePerformance:
    """Тесты производительности runtime"""
    
    @pytest.fixture
    async def fast_llm_client(self):
        """Mock быстрого LLM client для performance тестов"""
        client = AsyncMock()
        
        # Минимальная задержка для имитации реального LLM
        async def mock_chat(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms задержка
            return '{"content": "Fast response", "tool_calls": []}'
        
        client.chat = mock_chat
        
        async def mock_stream(*args, **kwargs):
            await asyncio.sleep(0.01)
            yield "Fast streaming response"
        
        client.chat_stream = mock_stream
        return client
    
    @pytest.fixture
    async def runtime(self, fast_llm_client):
        """AgentRuntime с быстрым mock LLM"""
        return AgentRuntime(llm_client=fast_llm_client)
    
    @pytest.fixture
    async def execution_request(self):
        """Оптимизированный ExecutionRequest для performance тестов"""
        from app.agents.router import AvailableActions, AvailableTool, EffectivePermissions
        
        request = MagicMock(spec=ExecutionRequest)
        request.agent = MagicMock()
        request.agent.slug = "perf-test-agent"
        request.agent_version = MagicMock()
        request.mode = ExecutionMode.FULL
        request.request_text = "Performance test"
        request.prompt = "Test prompt"
        
        # Минимальные available actions
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
        
        # Минимальные permissions
        permissions = MagicMock(spec=EffectivePermissions)
        permissions.allowed_tools = {"rag.search"}
        permissions.denied_reasons = {}
        request.effective_permissions = permissions
        
        # Оптимизированные policy
        request.policy_data = {"execution": {"max_steps": 5}}
        request.limit_data = {"limits": {"max_tool_calls": 10}}
        
        return request
    
    @pytest.fixture
    async def tool_context(self):
        """ToolContext для performance тестов"""
        return ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4())
        )
    
    async def test_simple_chat_performance(
        self,
        runtime,
        execution_request,
        tool_context
    ):
        """Тест производительности простого чата без tools"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock быстрый final response
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Измеряем время выполнения
            start_time = time.time()
            
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
            
            execution_time = time.time() - start_time
            
            # Проверяем производительность
            assert execution_time < 1.0, f"Simple chat too slow: {execution_time:.2f}s"
            assert len(events) > 0, "Should generate events"
            
            print(f"Simple chat execution time: {execution_time:.3f}s")
    
    async def test_tool_execution_performance(
        self,
        runtime,
        execution_request,
        tool_context
    ):
        """Тест производительности выполнения tools"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock tool execution
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            mock_next_action = NextAction(
                action_type=ActionType.TOOL,
                tool=ToolActionPayload(intent=MagicMock()),
                meta=ActionMeta(why="Performance test")
            )
            mock_next_action.tool.intent.tool_slug = "rag.search"
            mock_next_action.tool.intent.op = "run"
            mock_next_action.tool.input = {"query": "test"}
            
            mock_executor.execute_planner_with_fallback.return_value = mock_next_action
            
            with patch('app.agents.runtime.ToolRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                # Mock быстрый tool handler
                mock_tool_handler = AsyncMock()
                mock_tool_handler.slug = "rag.search"
                mock_router.select.return_value = mock_tool_handler
                
                from app.agents.context import ToolResult
                mock_tool_handler.execute.return_value = ToolResult(
                    success=True,
                    data={"results": ["test result"]},
                    metadata={}
                )
                
                # Измеряем время
                start_time = time.time()
                
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": "Search test"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    
                    # Останавливаем после tool execution
                    if event.type.value == "tool_result":
                        break
                
                execution_time = time.time() - start_time
                
                # Проверяем производительность
                assert execution_time < 2.0, f"Tool execution too slow: {execution_time:.2f}s"
                assert len(events) > 0, "Should generate events"
                
                print(f"Tool execution time: {execution_time:.3f}s")
    
    async def test_concurrent_execution_performance(
        self,
        runtime,
        execution_request,
        tool_context
    ):
        """Тест производительности при параллельном выполнении"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock быстрый response
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Создаем несколько concurrent запросов
            concurrent_requests = 5
            start_time = time.time()
            
            async def execute_request(request_id: int):
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": f"Concurrent request {request_id}"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    if event.type.value == "final":
                        break
                return len(events)
            
            # Выполняем параллельно
            tasks = [execute_request(i) for i in range(concurrent_requests)]
            results = await asyncio.gather(*tasks)
            
            execution_time = time.time() - start_time
            
            # Проверяем что параллельное выполнение быстрее последовательного
            assert execution_time < 3.0, f"Concurrent execution too slow: {execution_time:.2f}s"
            assert all(r > 0 for r in results), "All requests should generate events"
            
            print(f"Concurrent execution time ({concurrent_requests} requests): {execution_time:.3f}s")
            print(f"Average per request: {execution_time/concurrent_requests:.3f}s")
    
    async def test_memory_usage_stability(
        self,
        runtime,
        execution_request,
        tool_context
    ):
        """Тест стабильности использования памяти"""
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock response
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Выполняем несколько запросов
            num_requests = 20
            for i in range(num_requests):
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": f"Memory test {i}"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    if event.type.value == "final":
                        break
            
            # Проверяем memory usage
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            # Memory increase должен быть разумным (< 50MB для 20 запросов)
            assert memory_increase < 50, f"Memory leak detected: +{memory_increase:.1f}MB"
            
            print(f"Memory usage: {initial_memory:.1f}MB → {final_memory:.1f}MB (+{memory_increase:.1f}MB)")
    
    async def test_max_steps_performance_impact(
        self,
        runtime,
        execution_request,
        tool_context
    ):
        """Тест влияния max_steps на производительность"""
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            # Mock tool action для multiple steps
            from app.agents.contracts import NextAction, ActionType, ToolActionPayload, ActionMeta
            mock_next_action = NextAction(
                action_type=ActionType.TOOL,
                tool=ToolActionPayload(intent=MagicMock()),
                meta=ActionMeta(why="Performance test")
            )
            mock_next_action.tool.intent.tool_slug = "rag.search"
            mock_next_action.tool.intent.op = "run"
            mock_next_action.tool.input = {"query": "test"}
            
            mock_executor.execute_planner_with_fallback.return_value = mock_next_action
            
            with patch('app.agents.runtime.ToolRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                mock_tool_handler = AsyncMock()
                mock_tool_handler.slug = "rag.search"
                mock_router.select.return_value = mock_tool_handler
                
                from app.agents.context import ToolResult
                mock_tool_handler.execute.return_value = ToolResult(
                    success=True,
                    data={"results": ["test"]},
                    metadata={}
                )
                
                # Тестируем с разными max_steps
                max_steps_values = [1, 5, 10]
                performance_data = {}
                
                for max_steps in max_steps_values:
                    execution_request.policy_data = {"execution": {"max_steps": max_steps}}
                    
                    start_time = time.time()
                    step_count = 0
                    
                    async for event in runtime.run_with_planner(
                        exec_request=execution_request,
                        messages=[{"role": "user", "content": "Test"}],
                        ctx=tool_context,
                        enable_logging=False
                    ):
                        if event.type.value == "thinking":
                            step_count += 1
                        if step_count >= max_steps:
                            break
                    
                    execution_time = time.time() - start_time
                    performance_data[max_steps] = execution_time
                
                # Проверяем что время растет линейно, а не экспоненциально
                time_1 = performance_data[1]
                time_5 = performance_data[5]
                time_10 = performance_data[10]
                
                # Время не должно быть в 5 раз больше при увеличении steps в 5 раз
                assert time_5 < time_1 * 3, f"Performance degradation too high for 5 steps"
                assert time_10 < time_1 * 5, f"Performance degradation too high for 10 steps"
                
                print(f"Performance by max_steps: {performance_data}")


class TestRuntimeScalability:
    """Тесты масштабируемости runtime"""
    
    async def test_large_message_handling(self):
        """Тест обработки больших сообщений"""
        
        # Создаем большое сообщение
        large_content = "Test " * 10000  # ~50KB
        
        # Mock runtime с быстрым LLM
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = '{"content": "Response", "tool_calls": []}'
        
        runtime = AgentRuntime(llm_client=mock_llm)
        
        # Mock execution request
        execution_request = MagicMock()
        execution_request.agent = MagicMock()
        execution_request.agent.slug = "test-agent"
        execution_request.mode = ExecutionMode.FULL
        execution_request.available_actions = MagicMock()
        execution_request.available_actions.tools = []
        execution_request.effective_permissions = MagicMock()
        execution_request.effective_permissions.allowed_tools = set()
        execution_request.policy_data = {"execution": {"max_steps": 1}}
        execution_request.limit_data = {"limits": {"max_tool_calls": 1}}
        
        tool_context = ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4())
        )
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Измеряем время обработки большого сообщения
            start_time = time.time()
            
            events = []
            async for event in runtime.run_with_planner(
                exec_request=execution_request,
                messages=[{"role": "user", "content": large_content}],
                ctx=tool_context,
                enable_logging=False
            ):
                events.append(event)
                if event.type.value == "final":
                    break
            
            execution_time = time.time() - start_time
            
            # Обработка большого сообщения не должна быть слишком медленной
            assert execution_time < 2.0, f"Large message processing too slow: {execution_time:.2f}s"
            assert len(events) > 0, "Should handle large messages"
            
            print(f"Large message ({len(large_content)} chars) processing time: {execution_time:.3f}s")
    
    async def test_rapid_successive_requests(self):
        """Тест быстрых последовательных запросов"""
        
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = '{"content": "Quick response", "tool_calls": []}'
        
        runtime = AgentRuntime(llm_client=mock_llm)
        
        execution_request = MagicMock()
        execution_request.agent = MagicMock()
        execution_request.mode = ExecutionMode.FULL
        execution_request.available_actions = MagicMock()
        execution_request.available_actions.tools = []
        execution_request.effective_permissions = MagicMock()
        execution_request.effective_permissions.allowed_tools = set()
        execution_request.policy_data = {"execution": {"max_steps": 1}}
        execution_request.limit_data = {"limits": {"max_tool_calls": 1}}
        
        tool_context = ToolContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            chat_id=uuid4(),
            request_id=str(uuid4())
        )
        
        with patch('app.agents.runtime.SystemLLMExecutor') as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            
            from app.agents.contracts import NextAction, ActionType
            mock_executor.execute_planner_with_fallback.return_value = NextAction(
                action_type=ActionType.FINAL,
                final=MagicMock(),
                meta=MagicMock()
            )
            
            # Выполняем быстрые последовательные запросы
            num_requests = 50
            start_time = time.time()
            
            for i in range(num_requests):
                events = []
                async for event in runtime.run_with_planner(
                    exec_request=execution_request,
                    messages=[{"role": "user", "content": f"Quick request {i}"}],
                    ctx=tool_context,
                    enable_logging=False
                ):
                    events.append(event)
                    if event.type.value == "final":
                        break
            
            total_time = time.time() - start_time
            avg_time = total_time / num_requests
            
            # Среднее время на запрос должно быть низким
            assert avg_time < 0.1, f"Average request time too high: {avg_time:.3f}s"
            
            print(f"Rapid successive requests ({num_requests}): total={total_time:.2f}s, avg={avg_time:.3f}s")
