"""
AgentToolRuntime — автономный агент с operation-call loop.

Flow:
1. Build system prompt = agent prompt + collection blocks + operation instructions
2. Non-streaming LLM call
3. Parse operation_calls from response (protocol.py)
4. If operation_calls → execute each → add results to context → goto 2
5. If no operation_calls → streaming synthesis with operation data → final
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

MAX_OPERATION_RESULT_PREVIEW_CHARS = 4096


@dataclass
class AgentLoopState:
    """Mutable state for one agent execution loop."""
    operation_outputs: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[dict] = field(default_factory=list)
    operation_calls_total: int = 0
    steps_without_successful_tool_result: int = 0
    start_time: float = 0.0
    force_tool_choice: bool = False


from app.agents.protocol import (
    build_operation_results_message,
    build_tool_result_messages,
    build_tools_payload,
    parse_llm_response,
    parse_native_tool_calls,
)
from app.agents.runtime.tools import ConfirmationRequiredError
from app.agents.runtime.base import BaseRuntime
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.core.logging import get_logger
from app.runtime.budget import RuntimeBudgetTracker
from app.runtime.operation_errors import OperationResultEnvelope, RuntimeErrorCode

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)

MAX_STEPS_WITHOUT_SUCCESSFUL_TOOL_RESULT_DEFAULT = 2


class AgentToolRuntime(BaseRuntime):
    """Autonomous agent execution with operation-call loop."""

    async def execute(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        agent = exec_request.agent

        # Resolve config
        policy, gen, platform_config = await self.config_resolver.resolve(
            exec_request, ctx, model,
        )

        available_operations = exec_request.resolved_operations

        # System prompt
        sandbox_ov = ctx.get_runtime_deps().sandbox_overrides
        prompt_bundle = self.prompt_assembler.assemble(
            exec_request,
            sandbox_overrides=sandbox_ov,
            resolved_operations=available_operations,
            policy_limits=policy,
            platform_config=platform_config,
        )

        system_prompt = prompt_bundle.system_prompt

        # Logging
        resolved_logging_level = await self.logging_resolver.resolve_logging_level(
            ctx,
            getattr(agent, "logging_level", None),
        )
        run_session = self._create_run_session(
            ctx=ctx,
            agent_slug=agent.slug,
            mode="agent_with_operations",
            logging_level=resolved_logging_level.value,
            context_snapshot={
                "available_operations": [item.operation_slug for item in available_operations]
            },
            enable_logging=enable_logging,
        )
        await run_session.start()

        user_content = messages[-1].get("content", "") if messages else ""
        await run_session.log_step("user_request", {
            "content": user_content, "agent_slug": agent.slug,
            "mode": "agent_with_operations",
        })

        budget_payload = {
            "max_steps": policy.max_steps,
            "max_tool_calls_total": policy.max_tool_calls_total,
            "max_wall_time_ms": policy.max_wall_time_ms,
            "tool_timeout_ms": policy.tool_timeout_ms,
            "max_retries": policy.max_retries,
        }
        await run_session.log_step("budget_policy", budget_payload)
        yield RuntimeEvent(RuntimeEventType.STATUS, {
            "stage": "budget_policy",
            "policy": budget_payload,
        })

        if exec_request.partial_mode_warning:
            yield RuntimeEvent.status(
                "partial_mode",
                warning=exec_request.partial_mode_warning,
            )

        yield RuntimeEvent.status("agent_operation_loop_started")

        # Build working messages for LLM (mutable copy)
        llm_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ] + list(messages)

        loop_state = AgentLoopState()
        loop_state.start_time = time.time()  # Start clock after all setup is complete
        max_steps_without_success = int(
            platform_config.get("max_steps_without_successful_tool_result")
            or MAX_STEPS_WITHOUT_SUCCESSFUL_TOOL_RESULT_DEFAULT
        )
        fail_fast_invalid_calls = bool(
            platform_config.get("fail_fast_invalid_operation_calls", True)
        )
        native_tool_calling = bool(
            platform_config.get("native_tool_calling", False)
        ) and bool(available_operations)
        tools_payload = build_tools_payload(available_operations) if native_tool_calling else None
        runtime_budget = ctx.extra.get("runtime_budget_tracker")
        _saved_outer_budget = None
        if isinstance(runtime_budget, RuntimeBudgetTracker):
            _saved_outer_budget = runtime_budget.save_budget()
            runtime_budget.apply_agent_limits_inplace(
                max_steps=policy.max_steps,
                max_tool_calls_total=policy.max_tool_calls_total,
                tool_timeout_ms=policy.tool_timeout_ms,
                max_steps_without_success=max_steps_without_success,
            )
            budget_payload["shared_budget"] = runtime_budget.snapshot()
        tool_ledger = ctx.extra.get("runtime_tool_ledger")
        reuse_enabled = bool(ctx.extra.get("runtime_tool_reuse_enabled", True))

        try:
            for step in range(policy.max_steps):
                elapsed_ms = (time.time() - loop_state.start_time) * 1000
                global_remaining = (
                    runtime_budget.remaining_wall_time_ms()
                    if isinstance(runtime_budget, RuntimeBudgetTracker)
                    else policy.max_wall_time_ms
                )
                if elapsed_ms > policy.max_wall_time_ms or global_remaining <= 0:
                    yield RuntimeEvent.error(
                        "Wall time limit exceeded",
                        recoverable=False,
                        error_code=RuntimeErrorCode.AGENT_WALL_TIME_EXCEEDED,
                        retryable=False,
                    )
                    await run_session.finish("failed", "Wall time limit exceeded")
                    return

                yield RuntimeEvent.thinking(step + 1)
                if isinstance(runtime_budget, RuntimeBudgetTracker):
                    if not runtime_budget.can_run_agent_step():
                        yield RuntimeEvent.error(
                            "Agent step budget exhausted",
                            recoverable=False,
                            error_code=RuntimeErrorCode.AGENT_NO_SUCCESSFUL_OPERATION_RESULT,
                            retryable=False,
                        )
                        await run_session.finish("failed", "Agent step budget exhausted")
                        return
                    runtime_budget.record_agent_step()

                # Non-streaming LLM call to let agent decide
                llm_start = time.time()
                raw_response_dict: Optional[Dict[str, Any]] = None
                if native_tool_calling and tools_payload:
                    raw_response_dict = await self.llm.call_raw(
                        messages=llm_messages,
                        model=gen.model,
                        temperature=gen.temperature,
                        max_tokens=gen.max_tokens,
                        tools=tools_payload,
                        force_tool_choice=loop_state.force_tool_choice,
                    )
                    loop_state.force_tool_choice = False
                    raw_response = self.llm.normalize_response(raw_response_dict)
                else:
                    raw_response = await self.llm.call(
                        messages=llm_messages,
                        model=gen.model,
                        temperature=gen.temperature,
                        max_tokens=gen.max_tokens,
                    )
                llm_duration = int((time.time() - llm_start) * 1000)

                await run_session.log_step("llm_call", {
                    "step": step + 1,
                    "response_length": len(raw_response),
                    "native_tool_calling": native_tool_calling,
                }, duration_ms=llm_duration)

                # Parse operation calls — native path first, then text fallback
                strict_protocol = bool(platform_config.get("strict_operation_protocol", False))
                parsed = None
                if native_tool_calling and raw_response_dict is not None:
                    parsed = parse_native_tool_calls(raw_response_dict)
                if parsed is None:
                    parsed = parse_llm_response(raw_response, strict=strict_protocol)

                if not parsed.has_operation_calls:
                    if available_operations and not loop_state.operation_outputs:
                        loop_state.steps_without_successful_tool_result += 1
                        if loop_state.steps_without_successful_tool_result >= max_steps_without_success:
                            limit_message = (
                                "Agent repeatedly skipped required operation calls"
                            )
                            yield RuntimeEvent.error(
                                limit_message,
                                recoverable=False,
                                error_code=RuntimeErrorCode.AGENT_REQUIRED_OPERATION_CALL_MISSING,
                                retryable=False,
                            )
                            await run_session.log_step(
                                "budget_limit_exceeded",
                                {
                                    "kind": "required_operation_call_missing",
                                    "limit": max_steps_without_success,
                                    "consumed": loop_state.steps_without_successful_tool_result,
                                },
                            )
                            await run_session.finish("failed", limit_message)
                            return
                        if step + 1 >= policy.max_steps:
                            yield RuntimeEvent.error(
                                "Agent failed to call required operations before answering",
                                recoverable=False,
                                error_code=RuntimeErrorCode.AGENT_REQUIRED_OPERATION_CALL_MISSING,
                                retryable=False,
                            )
                            await run_session.finish(
                                "failed",
                                "no operation call before final answer",
                            )
                            return

                        llm_messages.append({"role": "assistant", "content": raw_response})
                        llm_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You must call at least one available operation before answering. "
                                    "Do not answer from prior knowledge. "
                                    "Choose the most relevant operation and return an operation call."
                                ),
                            }
                        )
                        if native_tool_calling:
                            loop_state.force_tool_choice = True
                        await run_session.log_step(
                            "protocol_retry",
                            {
                                "step": step + 1,
                                "reason": "no_operation_call_before_answer",
                                "available_operations": [
                                    item.operation_slug for item in available_operations
                                ],
                            },
                        )
                        continue

                    # No operation calls — agent decided to answer directly
                    async for ev in self._handle_no_operation_calls(
                        exec_request, messages, llm_messages,
                        parsed, loop_state.operation_outputs, loop_state.sources, gen, run_session, sandbox_ov,
                    ):
                        yield ev
                    await run_session.log_step("final_response", {
                        "step": step + 1, "operation_calls_total": len(loop_state.operation_outputs),
                    })
                    if isinstance(runtime_budget, RuntimeBudgetTracker):
                        budget_snapshot = runtime_budget.snapshot()
                        await run_session.log_step("budget_consumed", budget_snapshot)
                        yield RuntimeEvent.status("budget_consumed", budget=budget_snapshot)
                    await run_session.finish("completed")
                    return

                # Execute each operation call
                operation_results_for_context: List[tuple] = []
                successful_operation_results = 0
                non_retryable_operation_failures: List[Dict[str, str]] = []
                invalid_operation_slugs = [
                    call.operation_slug
                    for call in parsed.operation_calls
                    if not self._is_allowed_operation_call(call.operation_slug, available_operations)
                ]
                if fail_fast_invalid_calls and invalid_operation_slugs:
                    fail_message = (
                        "Agent requested unavailable operation(s): "
                        + ", ".join(invalid_operation_slugs[:5])
                    )
                    yield RuntimeEvent.error(
                        fail_message,
                        recoverable=False,
                        error_code=RuntimeErrorCode.OPERATION_UNAVAILABLE,
                        retryable=False,
                    )
                    await run_session.log_step(
                        "invalid_operation_call_fail_fast",
                        {
                            "step": step + 1,
                            "invalid_operation_slugs": invalid_operation_slugs[:10],
                        },
                    )
                    await run_session.finish("failed", fail_message)
                    return
                operation_calls_total_ref = [loop_state.operation_calls_total]
                for operation_call in parsed.operation_calls:
                    prev_outputs = len(loop_state.operation_outputs)
                    async for ev in self._execute_single_operation_call(
                        operation_call=operation_call,
                        ctx=ctx,
                        available_operations=available_operations,
                        policy=policy,
                        runtime_budget=runtime_budget,
                        run_session=run_session,
                        all_operation_outputs=loop_state.operation_outputs,
                        all_sources=loop_state.sources,
                        operation_results_for_context=operation_results_for_context,
                        operation_calls_total_ref=operation_calls_total_ref,
                    ):
                        yield ev
                        if ev.type in (
                            RuntimeEventType.ERROR,
                            RuntimeEventType.CONFIRMATION_REQUIRED,
                        ):
                            return
                    loop_state.operation_calls_total = operation_calls_total_ref[0]

                    new_entry = loop_state.operation_outputs[prev_outputs] if len(loop_state.operation_outputs) > prev_outputs else None
                    if new_entry is not None:
                        if new_entry.get("success"):
                            successful_operation_results += 1
                        else:
                            ec = str(new_entry.get("error_code") or "")
                            if (
                                ec in {
                                    RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
                                    RuntimeErrorCode.OPERATION_AMBIGUOUS.value,
                                    RuntimeErrorCode.OPERATION_EXECUTION_FAILED.value,
                                }
                                and new_entry.get("retryable") is False
                            ):
                                non_retryable_operation_failures.append(
                                    {
                                        "error_code": ec,
                                        "error": str(new_entry.get("error") or ""),
                                        "operation_slug": operation_call.operation_slug,
                                    }
                                )

                if successful_operation_results > 0:
                    loop_state.steps_without_successful_tool_result = 0
                else:
                    loop_state.steps_without_successful_tool_result += 1

                if (
                    fail_fast_invalid_calls
                    and non_retryable_operation_failures
                    and successful_operation_results == 0
                ):
                    primary = non_retryable_operation_failures[0]
                    fail_message = (
                        "Agent operation execution failed with non-retryable errors: "
                        + "; ".join(
                            f"{item['operation_slug']}[{item['error_code']}]"
                            for item in non_retryable_operation_failures[:3]
                        )
                    )
                    yield RuntimeEvent.error(
                        fail_message,
                        recoverable=False,
                        error_code=primary.get("error_code")
                        or RuntimeErrorCode.AGENT_NON_RETRYABLE_OPERATION_FAILURE,
                        retryable=False,
                    )
                    await run_session.log_step(
                        "invalid_operation_call_fail_fast",
                        {
                            "step": step + 1,
                            "errors": non_retryable_operation_failures[:5],
                        },
                    )
                    await run_session.finish("failed", fail_message)
                    return

                if loop_state.steps_without_successful_tool_result >= max_steps_without_success:
                    fail_message = (
                        "No successful operation results within the allowed retry budget"
                    )
                    yield RuntimeEvent.error(
                        fail_message,
                        recoverable=False,
                        error_code=RuntimeErrorCode.AGENT_NO_SUCCESSFUL_OPERATION_RESULT,
                        retryable=False,
                    )
                    await run_session.log_step(
                        "budget_limit_exceeded",
                        {
                            "kind": "no_successful_operation_result",
                            "limit": max_steps_without_success,
                            "consumed": loop_state.steps_without_successful_tool_result,
                        },
                    )
                    await run_session.finish("failed", fail_message)
                    return

                # Add operation results to LLM context and loop back.
                # Native path: assistant message with tool_calls + role=tool result messages.
                # Text path: assistant message + user message with formatted text blocks.
                if native_tool_calling and raw_response_dict is not None:
                    raw_tool_calls = (
                        ((raw_response_dict.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
                    )
                    assistant_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": raw_response or None,
                    }
                    if raw_tool_calls:
                        assistant_msg["tool_calls"] = raw_tool_calls
                    llm_messages.append(assistant_msg)
                    for tool_msg in build_tool_result_messages(operation_results_for_context, raw_tool_calls):
                        llm_messages.append(tool_msg)
                else:
                    results_message = build_operation_results_message(operation_results_for_context)
                    llm_messages.append({"role": "assistant", "content": raw_response})
                    llm_messages.append({"role": "user", "content": results_message})

                logger.info(
                    f"Agent operation loop step={step + 1}: "
                    f"{len(parsed.operation_calls)} operation calls executed, "
                    f"total_outputs={len(loop_state.operation_outputs)}",
                )
                if isinstance(runtime_budget, RuntimeBudgetTracker):
                    budget_snapshot = runtime_budget.snapshot()
                    await run_session.log_step("budget_consumed", budget_snapshot)
                    yield RuntimeEvent.status("budget_consumed", budget=budget_snapshot)

            # Max steps reached — synthesize with whatever we have
            if loop_state.operation_outputs:
                async for ev in self._synthesize_answer(
                    exec_request, messages, loop_state.operation_outputs, loop_state.sources, gen, run_session,
                ):
                    yield ev
            else:
                yield RuntimeEvent.error(
                    f"Maximum agent steps ({policy.max_steps}) reached without result",
                    recoverable=True,
                    error_code=RuntimeErrorCode.AGENT_NO_SUCCESSFUL_OPERATION_RESULT,
                    retryable=True,
                )
            if isinstance(runtime_budget, RuntimeBudgetTracker):
                budget_snapshot = runtime_budget.snapshot()
                await run_session.log_step("budget_consumed", budget_snapshot)
                yield RuntimeEvent.status("budget_consumed", budget=budget_snapshot)
            await run_session.finish("completed" if loop_state.operation_outputs else "failed")

        except Exception as e:
            logger.error(f"Agent operation loop failed: {e}", exc_info=True)
            yield RuntimeEvent.error(
                str(e),
                recoverable=False,
                error_code=RuntimeErrorCode.AGENT_RUNTIME_EXCEPTION,
                retryable=False,
            )
            await run_session.finish("failed", str(e))

        finally:
            if isinstance(runtime_budget, RuntimeBudgetTracker) and _saved_outer_budget is not None:
                runtime_budget.restore_budget(_saved_outer_budget)

    async def _execute_single_operation_call(
        self,
        *,
        operation_call: Any,
        ctx: "ToolContext",
        available_operations: List[Any],
        policy: Any,
        runtime_budget: Any,
        run_session: Any,
        all_operation_outputs: List[Dict[str, Any]],
        all_sources: List[dict],
        operation_results_for_context: List[tuple],
        operation_calls_total_ref: List[int],
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Execute one operation call: budget check → tool → SSE events → logging → collect."""
        # Per-policy budget check first (local, cheap), then global tracker.
        if operation_calls_total_ref[0] >= policy.max_tool_calls_total:
            limit_message = f"Maximum operation calls ({policy.max_tool_calls_total}) reached"
            yield RuntimeEvent.error(
                limit_message,
                recoverable=False,
                error_code=RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED,
                retryable=False,
            )
            await run_session.log_step("budget_limit_exceeded", {
                "kind": "max_tool_calls_total",
                "limit": policy.max_tool_calls_total,
                "consumed": operation_calls_total_ref[0],
            })
            await run_session.finish("failed", limit_message)
            return

        if isinstance(runtime_budget, RuntimeBudgetTracker) and not runtime_budget.can_consume_tool_call():
            limit_message = (
                f"Maximum operation calls ({runtime_budget.budget.max_tool_calls_total}) reached"
            )
            yield RuntimeEvent.error(
                limit_message,
                recoverable=False,
                error_code=RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED,
                retryable=False,
            )
            await run_session.log_step(
                "budget_limit_exceeded",
                {
                    "kind": "max_tool_calls_total",
                    "limit": runtime_budget.budget.max_tool_calls_total,
                    "consumed": runtime_budget.snapshot().get("consumed_tool_calls"),
                },
            )
            await run_session.finish("failed", limit_message)
            return

        yield RuntimeEvent.operation_call(
            operation_call.operation_slug,
            operation_call.id,
            operation_call.arguments,
        )
        await run_session.log_step("operation_call", {
            "operation_slug": operation_call.operation_slug,
            "call_id": operation_call.id,
            "arguments": operation_call.arguments,
            "input": operation_call.arguments,
        })

        try:
            result, sources = await self.tools.execute(
                operation_call, ctx, available_operations,
                timeout_s=(
                    int(
                        min(policy.tool_timeout_ms, runtime_budget.budget.per_tool_timeout_ms) / 1000
                    )
                    if policy.tool_timeout_ms and isinstance(runtime_budget, RuntimeBudgetTracker)
                    else int(policy.tool_timeout_ms / 1000) if policy.tool_timeout_ms else None
                ),
            )
        except ConfirmationRequiredError as exc:
            yield RuntimeEvent(RuntimeEventType.CONFIRMATION_REQUIRED, dict(exc.payload))
            await run_session.finish("waiting_confirmation", str(exc))
            return

        if not bool(result.metadata.get("reused")):
            operation_calls_total_ref[0] += 1
            if isinstance(runtime_budget, RuntimeBudgetTracker):
                runtime_budget.record_tool_call()

        raw_error_code = result.metadata.get("error_code")
        typed_error_code = None
        if raw_error_code:
            try:
                typed_error_code = RuntimeErrorCode(str(raw_error_code))
            except ValueError:
                typed_error_code = None
        envelope = OperationResultEnvelope(
            operation_slug=operation_call.operation_slug,
            call_id=operation_call.id,
            success=result.success,
            error_code=typed_error_code,
            safe_message=None if result.success else str(result.error or ""),
            retryable=(
                bool(result.metadata.get("retryable"))
                if "retryable" in result.metadata
                else None
            ),
            data=result.data if result.success else None,
        )
        sse_data = result.data if result.success else result.error
        sse_truncated = False
        if result.success and isinstance(sse_data, dict):
            try:
                raw_str = json.dumps(sse_data, ensure_ascii=False, default=str)
            except Exception:
                raw_str = str(sse_data)
            if len(raw_str) > MAX_OPERATION_RESULT_PREVIEW_CHARS:
                sse_data = raw_str[:MAX_OPERATION_RESULT_PREVIEW_CHARS]
                sse_truncated = True
        yield RuntimeEvent.operation_result(
            operation_call.operation_slug,
            operation_call.id,
            result.success,
            sse_data,
            reused=bool(result.metadata.get("reused")),
            reused_from_call_id=result.metadata.get("reused_from_call_id"),
            error_code=raw_error_code,
            retryable=result.metadata.get("retryable"),
            safe_message=None if result.success else str(result.error or ""),
            envelope=envelope.to_metadata(),
            truncated=sse_truncated if sse_truncated else None,
        )
        await run_session.log_step("operation_result", {
            "operation_slug": operation_call.operation_slug,
            "call_id": operation_call.id,
            "success": result.success,
            "reused": bool(result.metadata.get("reused")),
            "reused_from_call_id": result.metadata.get("reused_from_call_id"),
            "output": result.data if result.success else result.error,
            "result": result.data if result.success else result.error,
        })

        raw_output = result.data or {}
        all_operation_outputs.append({
            "operation": operation_call.operation_slug, "success": result.success,
            "data": raw_output, "error": result.error,
            "error_code": raw_error_code,
            "retryable": result.metadata.get("retryable"),
        })
        all_sources.extend(sources)
        result_text = self.tools.format_result_for_context(result)
        operation_results_for_context.append((operation_call, result_text))

    @staticmethod
    def _is_allowed_operation_call(operation_slug: str, available_operations: List[Any]) -> bool:
        from app.agents.runtime.tools import OperationExecutionFacade
        operation, _ = OperationExecutionFacade._find_operation(operation_slug, available_operations)
        return operation is not None

    async def _handle_no_operation_calls(
        self,
        exec_request: ExecutionRequest,
        original_messages: List[Dict[str, Any]],
        llm_messages: List[Dict[str, Any]],
        parsed: Any,
        all_operation_outputs: List[Dict[str, Any]],
        all_sources: List[dict],
        gen: GenerationParams,
        run_session: Any,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Handle case when agent decides not to call operations."""
        if all_operation_outputs:
            async for ev in self._synthesize_answer(
                exec_request, original_messages,
                all_operation_outputs, all_sources, gen, run_session, sandbox_overrides,
            ):
                yield ev
        elif parsed.text.strip():
            # Stream the agent's text response directly
            yield RuntimeEvent.status("generating_answer")
            yield RuntimeEvent.delta(parsed.text)
            yield RuntimeEvent.final(
                parsed.text,
                all_sources,
                run_id=str(exec_request.run_id),
            )
        else:
            # Empty response fallback — re-stream
            yield RuntimeEvent.status("generating_answer")
            full_content = ""
            async for chunk in self.llm.stream(
                messages=llm_messages,
                model=gen.model,
                temperature=gen.temperature,
                max_tokens=gen.max_tokens,
            ):
                full_content += chunk
                yield RuntimeEvent.delta(chunk)
            yield RuntimeEvent.final(
                full_content,
                all_sources,
                run_id=str(exec_request.run_id),
            )

    async def _synthesize_answer(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        tool_outputs: List[Dict[str, Any]],
        sources: List[dict],
        gen: GenerationParams,
        run_session: Any,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Stream a synthesis answer using operation outputs as grounding data."""
        agent_prompt = self.prompts.render_base_prompt(
            exec_request, sandbox_overrides=sandbox_overrides or {},
        )

        observation_text = self.tools.format_observation_text(tool_outputs)
        synthesis_messages = self.prompts.build_synthesis_messages(
            agent_prompt, list(messages), observation_text,
        )

        yield RuntimeEvent.status("generating_answer")
        answer_parts: List[str] = []
        async for chunk in self.llm.stream(
            messages=synthesis_messages, model=gen.model,
            temperature=gen.temperature, max_tokens=gen.max_tokens,
        ):
            answer_parts.append(chunk)
            yield RuntimeEvent.delta(chunk)

        full_answer = "".join(answer_parts)
        yield RuntimeEvent.final(
            full_answer,
            sources,
            run_id=str(exec_request.run_id),
        )
