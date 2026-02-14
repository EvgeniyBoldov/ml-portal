"""
Agent Runtime - ядро выполнения агентов с tool-call loop
"""
from __future__ import annotations
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING
from app.core.logging import get_logger
import uuid

from app.agents.context import ToolContext, ToolResult, ToolCall, RunContext

if TYPE_CHECKING:
    from app.services.run_store import RunStore
    from app.agents.router import ExecutionRequest
from app.agents.registry import ToolRegistry
from app.agents.protocol import (
    parse_llm_response,
    build_tools_prompt,
    build_tool_results_message,
)
from app.core.http.clients import LLMClientProtocol


@dataclass
class AgentProfile:
    """Legacy profile for backward compat with run() method.
    In v2, use run_with_request() which gets prompt from ExecutionRequest."""
    agent_slug: str
    prompt_text: str
    tools: List[str] = field(default_factory=list)
    generation_config: Dict[str, Any] = field(default_factory=dict)

logger = get_logger(__name__)


class RuntimeEventType(str, Enum):
    """Типы событий runtime"""
    STATUS = "status"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DELTA = "delta"
    FINAL = "final"
    ERROR = "error"


@dataclass
class RuntimeEvent:
    """
    Событие от AgentRuntime.
    Используется для стриминга прогресса выполнения.
    """
    type: RuntimeEventType
    data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def status(cls, stage: str, **extra) -> RuntimeEvent:
        return cls(RuntimeEventType.STATUS, {"stage": stage, **extra})
    
    @classmethod
    def thinking(cls, step: int) -> RuntimeEvent:
        return cls(RuntimeEventType.THINKING, {"step": step})
    
    @classmethod
    def tool_call(cls, tool_slug: str, call_id: str, arguments: dict) -> RuntimeEvent:
        return cls(RuntimeEventType.TOOL_CALL, {
            "tool": tool_slug,
            "call_id": call_id,
            "arguments": arguments
        })
    
    @classmethod
    def tool_result(cls, tool_slug: str, call_id: str, success: bool, data: Any) -> RuntimeEvent:
        return cls(RuntimeEventType.TOOL_RESULT, {
            "tool": tool_slug,
            "call_id": call_id,
            "success": success,
            "data": data
        })
    
    @classmethod
    def delta(cls, content: str) -> RuntimeEvent:
        return cls(RuntimeEventType.DELTA, {"content": content})
    
    @classmethod
    def final(cls, content: str, sources: Optional[List[dict]] = None) -> RuntimeEvent:
        return cls(RuntimeEventType.FINAL, {
            "content": content,
            "sources": sources or []
        })
    
    @classmethod
    def error(cls, message: str, recoverable: bool = False) -> RuntimeEvent:
        return cls(RuntimeEventType.ERROR, {
            "error": message,
            "recoverable": recoverable
        })


@dataclass
class PolicyLimits:
    """Extracted policy limits for runtime enforcement"""
    max_steps: int = 10
    max_tool_calls_total: int = 50
    max_wall_time_ms: int = 300000
    tool_timeout_ms: int = 30000
    max_retries: int = 3
    streaming_enabled: bool = True
    citations_required: bool = False
    allow_parallel_tool_calls: bool = False
    
    @classmethod
    def from_policy(cls, policy: Dict[str, Any], limit: Optional[Dict[str, Any]] = None) -> "PolicyLimits":
        """Extract limits from policy_data dict and optional limit_data dict.
        
        policy_data comes from PolicyVersion.policy_json (structured behavioral rules).
        limit_data comes from LimitVersion fields (execution constraints).
        limit_data values override policy_data values when both are present.
        """
        execution = policy.get("execution", {})
        retry = policy.get("retry", {})
        output = policy.get("output", {})
        tool_exec = policy.get("tool_execution", {})
        
        lim = limit or {}
        
        return cls(
            max_steps=lim.get("max_steps", execution.get("max_steps", 10)),
            max_tool_calls_total=lim.get("max_tool_calls", execution.get("max_tool_calls_total", 50)),
            max_wall_time_ms=lim.get("max_wall_time_ms", execution.get("max_wall_time_ms", 300000)),
            tool_timeout_ms=lim.get("tool_timeout_ms", execution.get("tool_timeout_ms", 30000)),
            max_retries=lim.get("max_retries", retry.get("max_retries", 3)),
            streaming_enabled=execution.get("streaming_enabled", True),
            citations_required=output.get("citations_required", False),
            allow_parallel_tool_calls=tool_exec.get("allow_parallel_tool_calls", False),
        )


class AgentRuntime:
    """
    Ядро выполнения агентов с tool-call loop.
    
    Основной flow:
    1. Собрать system prompt с инструкциями по tools
    2. Отправить запрос в LLM
    3. Если LLM вернул tool_calls:
       - Выполнить каждый tool
       - Добавить результаты в контекст
       - Повторить с шага 2
    4. Если LLM вернул финальный ответ - стримить его
    
    Использование:
        runtime = AgentRuntime(llm_client)
        async for event in runtime.run(profile, messages, ctx):
            handle_event(event)
            
    С ExecutionRequest (новый способ):
        exec_request = await router.route(agent_slug, user_id, tenant_id)
        async for event in runtime.run_with_request(exec_request, messages, ctx):
            handle_event(event)
    """
    
    DEFAULT_MAX_STEPS = 10
    
    def __init__(
        self,
        llm_client: LLMClientProtocol,
        max_steps: int = DEFAULT_MAX_STEPS,
        run_store: Optional["RunStore"] = None,
    ):
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.run_store = run_store
    
    async def run(
        self,
        profile: AgentProfile,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """
        Выполнить агента с tool-call loop (legacy flow без Router).
        
        Args:
            profile: Профиль агента (prompt, tools, config)
            messages: История сообщений (без system prompt)
            ctx: Контекст выполнения
            model: Override модели (опционально)
            enable_logging: Включить логирование run
            
        Yields:
            RuntimeEvent с прогрессом выполнения
        """
        from app.services.run_store import _hash_text
        
        run_ctx = RunContext()
        
        effective_model = model or profile.generation_config.get("model")
        
        tool_handlers = ToolRegistry.get_for_agent(profile.tools)
        tools_schemas = [h.to_llm_schema() for h in tool_handlers]
        
        logger.info(
            f"Starting agent run: {profile.agent_slug}, "
            f"tools: {[h.slug for h in tool_handlers]}, "
            f"model: {effective_model}"
        )
        
        # Start run logging if enabled
        run_id: Optional[uuid.UUID] = None
        should_log = enable_logging and self.run_store is not None
        
        if should_log:
            try:
                run_id = await self.run_store.start_run(
                    tenant_id=ctx.tenant_id,
                    agent_slug=profile.agent_slug,
                    user_id=ctx.user_id,
                    chat_id=ctx.chat_id,
                )
            except Exception as e:
                logger.warning(f"Failed to start run logging: {e}")
                should_log = False
        
        # Helper: safe step logging
        async def _log_step(
            step_type: str,
            data: Dict[str, Any],
            tokens_in: Optional[int] = None,
            tokens_out: Optional[int] = None,
            duration_ms: Optional[int] = None,
            error: Optional[str] = None,
        ) -> None:
            if should_log and run_id:
                try:
                    await self.run_store.add_step(
                        run_id, step_type, data,
                        tokens_in=tokens_in, tokens_out=tokens_out,
                        duration_ms=duration_ms, error=error,
                    )
                except Exception as e:
                    logger.warning(f"Failed to log step {step_type}: {e}")
        
        system_prompt = self._build_system_prompt(profile, tools_schemas)
        
        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        
        run_ctx.messages = llm_messages.copy()
        
        # Log user_request step
        user_content = messages[-1].get("content", "") if messages else ""
        await _log_step("user_request", {
            "content": user_content,
            "agent_slug": profile.agent_slug,
            "model": effective_model,
            "messages_count": len(messages),
        })
        
        step = 0
        collected_sources: List[dict] = []
        
        async def finish_run(status: str, error: Optional[str] = None):
            if should_log and run_id:
                try:
                    await self.run_store.finish_run(run_id, status=status, error=error)
                except Exception as e:
                    logger.warning(f"Failed to finish run logging: {e}")
        
        # Optimization: if no tools, skip tool-call loop and stream directly
        if not tool_handlers:
            logger.info("No tools configured, streaming directly")
            async for event in self._stream_final_response(
                llm_messages,
                effective_model,
                collected_sources
            ):
                yield event
            await finish_run("completed")
            return
        
        while step < self.max_steps:
            step += 1
            run_ctx.add_step("llm_request", {"step": step, "messages_count": len(llm_messages)})
            
            yield RuntimeEvent.thinking(step)
            
            # Log LLM request
            llm_start = time.time()
            await _log_step("llm_request", {
                "step": step,
                "model": effective_model,
                "messages_count": len(llm_messages),
                "messages": llm_messages,
                "system_prompt": system_prompt,
                "system_prompt_hash": _hash_text(system_prompt),
            })
            
            try:
                llm_response = await self._call_llm(llm_messages, effective_model)
            except Exception as e:
                llm_duration = int((time.time() - llm_start) * 1000)
                logger.error(f"LLM call failed: {e}", exc_info=True)
                await _log_step("llm_response", {
                    "step": step,
                    "error": str(e),
                    "has_tool_calls": False,
                }, duration_ms=llm_duration, error=str(e))
                yield RuntimeEvent.error(str(e))
                await finish_run("failed", str(e))
                return
            
            llm_duration = int((time.time() - llm_start) * 1000)
            parsed = parse_llm_response(llm_response)
            
            # Log LLM response
            await _log_step("llm_response", {
                "step": step,
                "content": llm_response,
                "content_length": len(llm_response),
                "has_tool_calls": parsed.has_tool_calls,
                "tool_calls_count": len(parsed.tool_calls) if parsed.has_tool_calls else 0,
                "is_final": parsed.is_final,
            }, duration_ms=llm_duration)
            
            if parsed.is_final:
                logger.info(f"Agent finished after {step} steps")
                
                stream_start = time.time()
                final_content = ""
                async for event in self._stream_final_response(
                    llm_messages, 
                    effective_model,
                    collected_sources
                ):
                    if event.type == RuntimeEventType.DELTA:
                        final_content += event.data.get("content", "")
                    yield event
                
                stream_duration = int((time.time() - stream_start) * 1000)
                await _log_step("final_response", {
                    "step": step,
                    "content": final_content,
                    "content_length": len(final_content),
                    "has_sources": bool(collected_sources),
                    "sources_count": len(collected_sources),
                }, duration_ms=stream_duration)
                
                await finish_run("completed")
                return
            
            logger.info(f"Step {step}: {len(parsed.tool_calls)} tool calls")
            
            tool_results = []
            for tc in parsed.tool_calls:
                _handler = next((h for h in tool_handlers if h.slug == tc.tool_slug), None)
                _schema_hash = getattr(_handler, 'schema_hash', None) if _handler else None
                
                yield RuntimeEvent.tool_call(tc.tool_slug, tc.id, tc.arguments)
                
                # Log tool call
                await _log_step("tool_call", {
                    "tool_slug": tc.tool_slug,
                    "call_id": tc.id,
                    "arguments": tc.arguments,
                    "schema_hash": _schema_hash,
                })
                
                tool_start = time.time()
                result, sources = await self._execute_tool(tc, ctx, tool_handlers)
                tool_duration = int((time.time() - tool_start) * 1000)
                
                if sources:
                    collected_sources.extend(sources)
                
                yield RuntimeEvent.tool_result(
                    tc.tool_slug, tc.id,
                    result.success,
                    result.data if result.success else result.error
                )
                
                # Log tool result (include tool_logs from ToolLogger)
                result_data = result.data if result.success else result.error
                tool_result_step = {
                    "tool_slug": tc.tool_slug,
                    "call_id": tc.id,
                    "success": result.success,
                    "result": result_data,
                    "has_sources": bool(sources),
                    "sources_count": len(sources) if sources else 0,
                }
                tool_logs = result.metadata.get("logs")
                if tool_logs:
                    tool_result_step["tool_logs"] = tool_logs
                    tool_result_step["tool_logs_count"] = len(tool_logs)
                
                await _log_step("tool_result", tool_result_step,
                    duration_ms=tool_duration,
                    error=result.error if not result.success else None)
                
                tool_results.append((tc, result.to_message_content()))
                run_ctx.increment_tool_calls()
            
            llm_messages.append({
                "role": "assistant",
                "content": llm_response
            })
            
            results_message = build_tool_results_message(tool_results)
            llm_messages.append({
                "role": "user",
                "content": results_message
            })
        
        logger.warning(f"Agent reached max steps ({self.max_steps})")
        await _log_step("error", {
            "error": f"Maximum steps ({self.max_steps}) reached",
            "step": step,
            "recoverable": True,
        }, error=f"Maximum steps ({self.max_steps}) reached")
        yield RuntimeEvent.error(
            f"Maximum steps ({self.max_steps}) reached",
            recoverable=True
        )
        await finish_run("failed", f"Maximum steps ({self.max_steps}) reached")
    
    def _build_system_prompt(
        self,
        profile: AgentProfile,
        tools_schemas: List[dict]
    ) -> str:
        """Собрать system prompt с инструкциями по tools"""
        base_prompt = profile.prompt_text
        
        if not tools_schemas:
            return base_prompt
        
        tools_instruction = build_tools_prompt(tools_schemas)
        
        return f"{base_prompt}\n\n{tools_instruction}"
    
    async def _call_llm(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str]
    ) -> str:
        """Вызвать LLM (non-streaming для парсинга tool calls)"""
        response = await self.llm_client.chat(messages, model=model)
        
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return response.get("content", "")
        
        return str(response)
    
    async def _stream_final_response(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str],
        sources: List[dict]
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Стримить финальный ответ"""
        yield RuntimeEvent.status("generating_answer")
        
        full_content = ""
        
        try:
            async for chunk in self.llm_client.chat_stream(messages, model=model):
                if chunk:
                    full_content += chunk
                    yield RuntimeEvent.delta(chunk)
        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            yield RuntimeEvent.error(str(e))
            return
        
        yield RuntimeEvent.final(full_content, sources)
    
    async def _execute_tool(
        self,
        tool_call: ToolCall,
        ctx: ToolContext,
        handlers: List
    ) -> tuple[ToolResult, List[dict]]:
        """
        Выполнить tool call.
        
        Returns:
            Tuple of (ToolResult, sources list for RAG-like tools)
            
        Tool logs (from ToolLogger) are automatically extracted from
        result.metadata["logs"] and available for RunStore persistence.
        """
        handler = None
        for h in handlers:
            if h.slug == tool_call.tool_slug:
                handler = h
                break
        
        if not handler:
            handler = ToolRegistry.get(tool_call.tool_slug)
        
        if not handler:
            logger.error(f"Tool not found: {tool_call.tool_slug}")
            return ToolResult.fail(f"Tool '{tool_call.tool_slug}' not found"), []
        
        validation_error = handler.validate_args(tool_call.arguments)
        if validation_error:
            logger.warning(f"Tool args validation failed: {validation_error}")
            return ToolResult.fail(validation_error), []
        
        try:
            logger.info(f"Executing tool: {tool_call.tool_slug}")
            result = await handler.execute(ctx, tool_call.arguments)
            
            sources = []
            if result.success and result.metadata.get("sources"):
                sources = result.metadata["sources"]
            
            # Log tool-level entries to structured logger
            tool_logs = result.metadata.get("logs")
            if tool_logs:
                log_summary = [
                    e for e in tool_logs if e.get("level") in ("warning", "error")
                ]
                if log_summary:
                    logger.info(
                        f"Tool {tool_call.tool_slug} produced {len(tool_logs)} log entries "
                        f"({len(log_summary)} warnings/errors)"
                    )
            
            return result, sources
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return ToolResult.fail(str(e)), []
    
    async def run_with_request(
        self,
        exec_request: "ExecutionRequest",
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """
        Выполнить агента с ExecutionRequest от Router.
        
        Применяет policy limits из агента и использует
        только доступные tools из exec_request.
        Логирует каждый шаг в RunStore с учётом logging_level агента.
        
        Args:
            exec_request: ExecutionRequest от AgentRouter
            messages: История сообщений (без system prompt)
            ctx: Контекст выполнения
            model: Override модели (опционально)
            enable_logging: Включить логирование run
            
        Yields:
            RuntimeEvent с прогрессом выполнения
        """
        from app.agents.router import ExecutionMode
        from app.services.run_store import _hash_text
        
        agent = exec_request.agent
        
        # Extract policy limits from exec_request (resolved by AgentRouter)
        policy = PolicyLimits.from_policy(
            exec_request.policy_data,
            exec_request.limit_data,
        )
        
        # Override max_steps from policy
        original_max_steps = self.max_steps
        self.max_steps = policy.max_steps
        
        run_ctx = RunContext()
        start_time = time.time()
        total_tool_calls = 0
        
        effective_model = model
        
        # Use only available tools from exec_request
        available_tool_slugs = [t.tool_slug for t in exec_request.available_tools]
        tool_handlers = ToolRegistry.get_for_agent(available_tool_slugs)
        tools_schemas = [h.to_llm_schema() for h in tool_handlers]
        
        # Resolve logging level from Agent
        logging_level = getattr(agent, 'logging_level', 'brief') or 'brief'
        
        logger.info(
            f"Starting agent run with ExecutionRequest: {agent.slug}, "
            f"mode: {exec_request.mode.value}, "
            f"tools: {available_tool_slugs}, "
            f"logging: {logging_level}, "
            f"policy: max_steps={policy.max_steps}, max_tool_calls={policy.max_tool_calls_total}"
        )
        
        # Build context snapshot for reproducibility
        context_snapshot = {
            "agent_slug": agent.slug,
            "agent_version_id": str(agent.current_version_id) if agent.current_version_id else None,
            "prompt_hash": _hash_text(exec_request.prompt) if exec_request.prompt else None,
            "model": effective_model,
            "execution_mode": exec_request.mode.value,
            "policy": {
                "max_steps": policy.max_steps,
                "max_tool_calls": policy.max_tool_calls_total,
                "max_wall_time_ms": policy.max_wall_time_ms,
                "tool_timeout_ms": policy.tool_timeout_ms,
                "streaming_enabled": policy.streaming_enabled,
            },
            "policy_data_hash": _hash_text(str(exec_request.policy_data)) if exec_request.policy_data else None,
            "limit_data_hash": _hash_text(str(exec_request.limit_data)) if exec_request.limit_data else None,
            "tools": [
                {
                    "slug": t.tool_slug,
                    "instance_id": str(t.instance_id) if t.instance_id else None,
                    "has_credentials": t.has_credentials,
                }
                for t in exec_request.available_tools
            ],
            "permissions": {
                "allowed_tools": list(exec_request.effective_permissions.allowed_tools) if exec_request.effective_permissions else [],
                "denied_reasons": exec_request.effective_permissions.denied_reasons if exec_request.effective_permissions else {},
            },
            "routing_duration_ms": exec_request.routing_duration_ms,
            "routing_reasons": exec_request.routing_reasons,
        }
        
        # Start run logging
        run_id: Optional[uuid.UUID] = None
        should_log = enable_logging and self.run_store is not None
        
        if should_log:
            try:
                run_id = await self.run_store.start_run(
                    tenant_id=ctx.tenant_id,
                    agent_slug=agent.slug,
                    logging_level=logging_level,
                    user_id=ctx.user_id,
                    chat_id=ctx.chat_id,
                    context_snapshot=context_snapshot,
                )
            except Exception as e:
                logger.warning(f"Failed to start run logging: {e}")
                should_log = False
        
        # Helper: safe step logging (never breaks runtime on log failure)
        async def _log_step(
            step_type: str,
            data: Dict[str, Any],
            tokens_in: Optional[int] = None,
            tokens_out: Optional[int] = None,
            duration_ms: Optional[int] = None,
            error: Optional[str] = None,
        ) -> None:
            if should_log and run_id:
                try:
                    await self.run_store.add_step(
                        run_id, step_type, data,
                        tokens_in=tokens_in, tokens_out=tokens_out,
                        duration_ms=duration_ms, error=error,
                    )
                except Exception as e:
                    logger.warning(f"Failed to log step {step_type}: {e}")
        
        # Log user_request step
        user_content = messages[-1].get("content", "") if messages else ""
        await _log_step("user_request", {
            "content": user_content,
            "agent_slug": agent.slug,
            "model": effective_model,
            "messages_count": len(messages),
        })
        
        # Log routing step
        await _log_step("routing", {
            "mode": exec_request.mode.value,
            "available_tools": available_tool_slugs,
            "permissions": context_snapshot.get("permissions", {}),
            "policy": context_snapshot.get("policy", {}),
            "routing_reasons": exec_request.routing_reasons,
            "duration_ms": exec_request.routing_duration_ms,
            "partial_warning": exec_request.partial_mode_warning,
        }, duration_ms=exec_request.routing_duration_ms)
        
        # Build system prompt from exec_request (v2: prompt is in AgentVersion)
        base_prompt = getattr(exec_request, 'prompt', '') or "You are an AI assistant."
        
        if tools_schemas:
            tools_instruction = build_tools_prompt(tools_schemas)
            system_prompt = f"{base_prompt}\n\n{tools_instruction}"
        else:
            system_prompt = base_prompt
        
        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(messages)
        
        run_ctx.messages = llm_messages.copy()
        
        step = 0
        collected_sources: List[dict] = []
        
        async def finish_run(status: str, error: Optional[str] = None):
            if should_log and run_id:
                try:
                    await self.run_store.finish_run(run_id, status=status, error=error)
                except Exception as e:
                    logger.warning(f"Failed to finish run logging: {e}")
        
        async def check_policy_limits() -> Optional[RuntimeEvent]:
            """Check if policy limits are exceeded"""
            elapsed_ms = (time.time() - start_time) * 1000
            
            if elapsed_ms > policy.max_wall_time_ms:
                return RuntimeEvent.error(
                    f"Wall time limit exceeded ({policy.max_wall_time_ms}ms)",
                    recoverable=False
                )
            
            if total_tool_calls >= policy.max_tool_calls_total:
                return RuntimeEvent.error(
                    f"Tool calls limit exceeded ({policy.max_tool_calls_total})",
                    recoverable=False
                )
            
            return None
        
        # Emit partial mode warning if present
        if exec_request.partial_mode_warning:
            logger.info(f"Partial mode: {exec_request.partial_mode_warning}")
            yield RuntimeEvent.status("partial_mode_warning", warning=exec_request.partial_mode_warning)
        
        # If no tools, stream directly
        if not tool_handlers:
            logger.info("No tools available, streaming directly")
            async for event in self._stream_final_response(
                llm_messages, effective_model, collected_sources
            ):
                yield event
            await _log_step("final_response", {
                "step": 0,
                "content_length": 0,
                "has_sources": bool(collected_sources),
                "sources_count": len(collected_sources),
                "no_tools": True,
            })
            await finish_run("completed")
            self.max_steps = original_max_steps
            return
        
        try:
            while step < self.max_steps:
                step += 1
                
                # Check policy limits
                limit_error = await check_policy_limits()
                if limit_error:
                    await _log_step("error", {
                        "error": limit_error.data.get("error"),
                        "step": step,
                        "recoverable": False,
                    }, error=limit_error.data.get("error"))
                    yield limit_error
                    await finish_run("failed", limit_error.data.get("error"))
                    return
                
                yield RuntimeEvent.thinking(step)
                
                # Log LLM request
                llm_start = time.time()
                await _log_step("llm_request", {
                    "step": step,
                    "model": effective_model,
                    "messages_count": len(llm_messages),
                    "messages": llm_messages,
                    "system_prompt": system_prompt,
                    "system_prompt_hash": _hash_text(system_prompt),
                })
                
                try:
                    llm_response = await self._call_llm(llm_messages, effective_model)
                except Exception as e:
                    llm_duration = int((time.time() - llm_start) * 1000)
                    logger.error(f"LLM call failed: {e}", exc_info=True)
                    await _log_step("llm_response", {
                        "step": step,
                        "error": str(e),
                        "has_tool_calls": False,
                    }, duration_ms=llm_duration, error=str(e))
                    yield RuntimeEvent.error(str(e))
                    await finish_run("failed", str(e))
                    return
                
                llm_duration = int((time.time() - llm_start) * 1000)
                parsed = parse_llm_response(llm_response)
                
                # Log LLM response
                await _log_step("llm_response", {
                    "step": step,
                    "content": llm_response,
                    "content_length": len(llm_response),
                    "has_tool_calls": parsed.has_tool_calls,
                    "tool_calls_count": len(parsed.tool_calls) if parsed.has_tool_calls else 0,
                    "is_final": parsed.is_final,
                }, duration_ms=llm_duration)
                
                logger.info(
                    f"LLM response (step {step}): has_tool_calls={parsed.has_tool_calls}, "
                    f"response_len={len(llm_response)}, duration={llm_duration}ms"
                )
                
                if parsed.is_final:
                    logger.info(f"Agent finished after {step} steps, {total_tool_calls} tool calls")
                    
                    stream_start = time.time()
                    final_content = ""
                    async for event in self._stream_final_response(
                        llm_messages, effective_model, collected_sources
                    ):
                        if event.type == RuntimeEventType.DELTA:
                            final_content += event.data.get("content", "")
                        yield event
                    
                    stream_duration = int((time.time() - stream_start) * 1000)
                    await _log_step("final_response", {
                        "step": step,
                        "content": final_content,
                        "content_length": len(final_content),
                        "has_sources": bool(collected_sources),
                        "sources_count": len(collected_sources),
                    }, duration_ms=stream_duration)
                    
                    await finish_run("completed")
                    return
                
                logger.info(f"Step {step}: {len(parsed.tool_calls)} tool calls")
                
                tool_results = []
                for tc in parsed.tool_calls:
                    # Check if tool is in available tools
                    if tc.tool_slug not in available_tool_slugs:
                        logger.warning(f"Tool {tc.tool_slug} not available, skipping")
                        tool_results.append((
                            tc,
                            f"Tool '{tc.tool_slug}' is not available for this agent"
                        ))
                        continue
                    
                    total_tool_calls += 1
                    
                    # Check tool calls limit
                    if total_tool_calls > policy.max_tool_calls_total:
                        await _log_step("error", {
                            "error": "Tool calls limit exceeded",
                            "step": step,
                            "total_tool_calls": total_tool_calls,
                        }, error="Tool calls limit exceeded")
                        yield RuntimeEvent.error(
                            f"Tool calls limit exceeded ({policy.max_tool_calls_total})",
                            recoverable=False
                        )
                        await finish_run("failed", "Tool calls limit exceeded")
                        return
                    
                    # Resolve handler for schema_hash logging
                    _handler = next((h for h in tool_handlers if h.slug == tc.tool_slug), None)
                    _schema_hash = getattr(_handler, 'schema_hash', None) if _handler else None
                    
                    yield RuntimeEvent.tool_call(
                        tc.tool_slug,
                        tc.id,
                        tc.arguments
                    )
                    
                    # Log tool call
                    await _log_step("tool_call", {
                        "tool_slug": tc.tool_slug,
                        "call_id": tc.id,
                        "arguments": tc.arguments,
                        "schema_hash": _schema_hash,
                    })
                    
                    tool_start = time.time()
                    result, sources = await self._execute_tool(tc, ctx, tool_handlers)
                    tool_duration = int((time.time() - tool_start) * 1000)
                    
                    if sources:
                        collected_sources.extend(sources)
                    
                    yield RuntimeEvent.tool_result(
                        tc.tool_slug,
                        tc.id,
                        result.success,
                        result.data if result.success else result.error
                    )
                    
                    # Log tool result (include tool_logs from ToolLogger)
                    result_data = result.data if result.success else result.error
                    tool_result_step = {
                        "tool_slug": tc.tool_slug,
                        "call_id": tc.id,
                        "success": result.success,
                        "result": result_data,
                        "has_sources": bool(sources),
                        "sources_count": len(sources) if sources else 0,
                    }
                    tool_logs = result.metadata.get("logs")
                    if tool_logs:
                        tool_result_step["tool_logs"] = tool_logs
                        tool_result_step["tool_logs_count"] = len(tool_logs)
                    
                    await _log_step("tool_result", tool_result_step,
                        duration_ms=tool_duration,
                        error=result.error if not result.success else None)
                    
                    tool_results.append((tc, result.to_message_content()))
                    run_ctx.increment_tool_calls()
                
                llm_messages.append({
                    "role": "assistant",
                    "content": llm_response
                })
                
                results_message = build_tool_results_message(tool_results)
                llm_messages.append({
                    "role": "user",
                    "content": results_message
                })
            
            logger.warning(f"Agent reached max steps ({self.max_steps})")
            await _log_step("error", {
                "error": f"Maximum steps ({self.max_steps}) reached",
                "step": step,
                "recoverable": True,
            }, error=f"Maximum steps ({self.max_steps}) reached")
            yield RuntimeEvent.error(
                f"Maximum steps ({self.max_steps}) reached",
                recoverable=True
            )
            await finish_run("failed", f"Maximum steps ({self.max_steps}) reached")
            
        finally:
            # Restore original max_steps
            self.max_steps = original_max_steps
