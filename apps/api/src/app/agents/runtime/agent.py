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
    retry_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_total: int = 0
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
from app.agents.runtime.published_capabilities import (
    serialize_published_collections,
    serialize_published_operations,
)
from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.core.logging import get_logger
from app.models.execution_limit import ExecutionLimitScope
from app.runtime.context_snapshot import compact_snapshot
from app.runtime.budgets import RunBudgetLedger
from app.runtime.llm.limits import LLMLimitExceededError, apply_llm_limits
from app.runtime.operation_errors import OperationResultEnvelope, RuntimeErrorCode
from app.services.execution_limits_service import ExecutionLimitsPayload, ExecutionLimitsService, apply_limits_override
from app.services.platform_settings_defaults import (
    PLATFORM_INTENT_MESSAGES,
    PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION,
)

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)

MAX_STEPS_WITHOUT_SUCCESSFUL_TOOL_RESULT_DEFAULT = 2
DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION = PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION
DEFAULT_INTENT_MESSAGES = PLATFORM_INTENT_MESSAGES


def _estimate_tokens(text: str) -> int:
    raw = (text or "").strip()
    if not raw:
        return 0
    return max(1, len(raw) // 4)


def _build_budget_snapshot_payload(
    *,
    owner_id: str,
    reason: str,
    step: int,
    policy: PolicyLimits,
    loop_state: AgentLoopState,
    start_time: Optional[float] = None,
    delta: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    if not start_time:
        start_time = loop_state.start_time or time.time()
    used_wall_time_ms = int((time.time() - start_time) * 1000)
    return {
        "owner_scope": "agent",
        "owner_id": owner_id,
        "parent_entity_type": "agent_run",
        "parent_entity_id": owner_id,
        "snapshot": {
            "agent_steps": {
                "used": step,
                "limit": policy.max_steps,
                "remaining": max(0, policy.max_steps - step),
            },
            "tool_calls": {
                "used": loop_state.operation_calls_total,
                "limit": policy.max_tool_calls_total,
                "remaining": max(0, policy.max_tool_calls_total - loop_state.operation_calls_total),
            },
            "retries": {
                "used": loop_state.retry_count,
                "limit": policy.max_retries,
                "remaining": max(0, policy.max_retries - loop_state.retry_count),
            },
            "tokens_in": {
                "used": loop_state.tokens_in,
                "limit": None,
                "remaining": None,
            },
            "tokens_out": {
                "used": loop_state.tokens_out,
                "limit": None,
                "remaining": None,
            },
            "tokens_total": {
                "used": loop_state.tokens_total,
                "limit": None,
                "remaining": None,
            },
            "wall_time_ms": {
                "used": used_wall_time_ms,
                "limit": policy.max_wall_time_ms,
                "remaining": max(0, policy.max_wall_time_ms - used_wall_time_ms),
            },
        },
        "delta": delta or {},
        "reason": reason,
        "at_ms": int(time.time() * 1000),
    }


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
            context_snapshot=compact_snapshot(
                meta={
                    "available_operations": serialize_published_operations(available_operations),
                    "available_collections": serialize_published_collections(
                        exec_request.resolved_data_instances,
                        available_operations,
                    ),
                },
            ),
            enable_logging=enable_logging,
        )
        await run_session.start()
        agent_event_ctx = {
            "agent_slug": agent.slug,
            "agent_run_id": str(run_session.run_id) if run_session.run_id else None,
        }
        
        # Add run_id to context for intent logging
        if run_session.run_id:
            ctx.extra["run_id"] = run_session.run_id

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
        budget_owner_id = str(run_session.run_id) if run_session.run_id else f"agent:{agent.slug}"
        init_budget_snapshot = _build_budget_snapshot_payload(
            owner_id=budget_owner_id,
            reason="init",
            step=0,
            policy=policy,
            loop_state=AgentLoopState(start_time=time.time()),
        )
        await run_session.log_step("budget_snapshot", init_budget_snapshot)
        yield RuntimeEvent(RuntimeEventType.BUDGET_SNAPSHOT, init_budget_snapshot)

        if exec_request.partial_mode_warning:
            yield RuntimeEvent.status(
                "partial_mode",
                warning=exec_request.partial_mode_warning,
                **agent_event_ctx,
            )

        yield RuntimeEvent.status("agent_operation_loop_started", **agent_event_ctx)
        
        # Log high-level intent
        await ctx.log_intent(
            self._intent_message(
                key="agent_start",
                platform_config=platform_config,
                sandbox_overrides=sandbox_ov,
            ),
            {"agent_slug": agent.slug, "operations_count": len(available_operations)}
        )

        # Build working messages for LLM (mutable copy)
        llm_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ] + list(messages)
        llm_limits = await self._resolve_llm_limits_for_agent(ctx=ctx, agent_slug=agent.slug)

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
        runtime_budget = ctx.extra.get("runtime_budget_ledger")
        if isinstance(runtime_budget, RunBudgetLedger):
            budget_payload["shared_budget"] = runtime_budget.snapshot()
        tool_ledger = ctx.extra.get("runtime_tool_ledger")
        reuse_enabled = bool(ctx.extra.get("runtime_tool_reuse_enabled", True))

        try:
            for step in range(policy.max_steps):
                llm_call_id = (
                    f"{run_session.run_id}:agent-llm:{step + 1}"
                    if run_session.run_id
                    else f"agent-llm:{step + 1}"
                )
                elapsed_ms = (time.time() - loop_state.start_time) * 1000
                global_remaining = (
                    runtime_budget.remaining_wall_time_ms()
                    if isinstance(runtime_budget, RunBudgetLedger)
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

                if isinstance(runtime_budget, RunBudgetLedger):
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
                step_budget_snapshot = _build_budget_snapshot_payload(
                    owner_id=budget_owner_id,
                    reason="agent_step",
                    step=step + 1,
                    policy=policy,
                    loop_state=loop_state,
                    start_time=loop_state.start_time,
                    delta={"agent_steps": 1},
                )
                await run_session.log_step("budget_snapshot", step_budget_snapshot)
                yield RuntimeEvent(RuntimeEventType.BUDGET_SNAPSHOT, step_budget_snapshot)

                # Non-streaming LLM call to let agent decide
                llm_start = time.time()
                try:
                    boundary = apply_llm_limits(
                        limits=llm_limits,
                        input_tokens=_estimate_tokens(json.dumps(llm_messages, ensure_ascii=False, default=str)),
                        requested_output_tokens=gen.max_tokens,
                    )
                except LLMLimitExceededError as exc:
                    yield RuntimeEvent.error(
                        str(exc),
                        recoverable=False,
                        error_code=exc.code,
                        retryable=False,
                    )
                    await run_session.finish("failed", str(exc))
                    return
                effective_max_tokens = boundary.output_tokens if boundary.output_tokens is not None else gen.max_tokens
                raw_response_dict: Optional[Dict[str, Any]] = None
                if native_tool_calling and tools_payload:
                    raw_response_dict = await self.llm.call_raw(
                        messages=llm_messages,
                        model=gen.model,
                        temperature=gen.temperature,
                        max_tokens=effective_max_tokens,
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
                        max_tokens=effective_max_tokens,
                    )
                llm_duration = int((time.time() - llm_start) * 1000)
                usage = (raw_response_dict or {}).get("usage") if isinstance(raw_response_dict, dict) else None
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0
                if isinstance(usage, dict):
                    prompt_tokens = int(usage.get("prompt_tokens") or 0)
                    completion_tokens = int(usage.get("completion_tokens") or 0)
                    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
                else:
                    # Provider usage is not always present (e.g. non-native path).
                    # Keep a deterministic heuristic so trace/token budgets remain informative.
                    prompt_tokens = _estimate_tokens(json.dumps(llm_messages, ensure_ascii=False, default=str))
                    completion_tokens = _estimate_tokens(raw_response or "")
                    total_tokens = prompt_tokens + completion_tokens
                loop_state.tokens_in += max(0, prompt_tokens)
                loop_state.tokens_out += max(0, completion_tokens)
                loop_state.tokens_total += max(0, total_tokens)
                if isinstance(runtime_budget, RunBudgetLedger):
                    runtime_budget.record_tokens(
                        tokens_in=max(0, prompt_tokens),
                        tokens_out=max(0, completion_tokens),
                        owner_id=budget_owner_id,
                    )

                await run_session.log_step("llm_turn", {
                    "step": step + 1,
                    "model": gen.model,
                    "temperature": gen.temperature,
                    "max_tokens": effective_max_tokens,
                    "messages": llm_messages,
                    "content": raw_response,
                    "response_length": len(raw_response),
                    "native_tool_calling": native_tool_calling,
                    "llm_call_id": llm_call_id,
                    "parent_entity_type": "agent_run",
                    "parent_entity_id": str(run_session.run_id) if run_session.run_id else None,
                    "agent_run_id": str(run_session.run_id) if run_session.run_id else None,
                    "agent_slug": agent.slug,
                    "tokens_in": max(0, prompt_tokens),
                    "tokens_out": max(0, completion_tokens),
                    "tokens_total": max(0, total_tokens),
                    "purpose": "tool_decision_or_answer",
                    "actor_type": "agent",
                    "actor_entity_id": str(run_session.run_id) if run_session.run_id else None,
                }, duration_ms=llm_duration, tokens_in=max(0, prompt_tokens), tokens_out=max(0, completion_tokens))
                yield RuntimeEvent.llm_turn(
                    llm_call_id=llm_call_id,
                    step=step + 1,
                    model=gen.model,
                    temperature=gen.temperature,
                    max_tokens=effective_max_tokens,
                    messages=llm_messages,
                    content=raw_response,
                    response_length=len(raw_response),
                    tokens_in=max(0, prompt_tokens),
                    tokens_out=max(0, completion_tokens),
                    tokens_total=max(0, total_tokens),
                    native_tool_calling=native_tool_calling,
                    duration_ms=llm_duration,
                    parent_entity_type="agent_run",
                    parent_entity_id=str(run_session.run_id) if run_session.run_id else None,
                    agent_run_id=str(run_session.run_id) if run_session.run_id else None,
                    agent_slug=agent.slug,
                    purpose="tool_decision_or_answer",
                    actor_type="agent",
                    actor_entity_id=str(run_session.run_id) if run_session.run_id else None,
                )

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
                            await run_session.log_step("budget_snapshot", _build_budget_snapshot_payload(
                                owner_id=budget_owner_id,
                                reason="limit_exceeded",
                                step=step + 1,
                                policy=policy,
                                loop_state=loop_state,
                                start_time=loop_state.start_time,
                                delta={},
                            ))
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
                                "content": self._required_operation_retry_instruction(
                                    platform_config=platform_config,
                                    sandbox_overrides=sandbox_ov,
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
                                "available_operations": serialize_published_operations(available_operations),
                            },
                        )
                        loop_state.retry_count += 1
                        if isinstance(runtime_budget, RunBudgetLedger):
                            runtime_budget.record_retry(owner_id=budget_owner_id)
                        continue

                    # No operation calls — agent decided to answer directly
                    await ctx.log_intent(
                        self._intent_message(
                            key="final_answer",
                            platform_config=platform_config,
                            sandbox_overrides=sandbox_ov,
                        ),
                        {"step": step + 1, "operation_calls_total": len(loop_state.operation_outputs)}
                    )
                    final_answer_content: List[str] = []
                    async for ev in self._handle_no_operation_calls(
                        exec_request, messages, llm_messages,
                        parsed, loop_state.operation_outputs, loop_state.sources, gen, run_session, sandbox_ov,
                    ):
                        if ev.type == RuntimeEventType.FINAL and isinstance(ev.data, dict):
                            final_answer_content.append(str(ev.data.get("content", "") or ""))
                        yield ev
                    await run_session.log_step("final_response", {
                        "step": step + 1,
                        "operation_calls_total": len(loop_state.operation_outputs),
                        "content": final_answer_content[0] if final_answer_content else "",
                    })
                    if isinstance(runtime_budget, RunBudgetLedger):
                        final_budget_snapshot = _build_budget_snapshot_payload(
                            owner_id=budget_owner_id,
                            reason="final",
                            step=step + 1,
                            policy=policy,
                            loop_state=loop_state,
                            start_time=loop_state.start_time,
                        )
                        await run_session.log_step("budget_snapshot", final_budget_snapshot)
                        yield RuntimeEvent(RuntimeEventType.BUDGET_SNAPSHOT, final_budget_snapshot)
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
                    # Log intent before executing each operation
                    await ctx.log_intent(
                        self._intent_message(
                            key="operation_call",
                            platform_config=platform_config,
                            sandbox_overrides=sandbox_ov,
                            operation_slug=operation_call.operation_slug,
                        ),
                        {"arguments": operation_call.arguments}
                    )
                    
                    prev_outputs = len(loop_state.operation_outputs)
                    async for ev in self._execute_single_operation_call(
                        operation_call=operation_call,
                        agent_slug=agent.slug,
                        agent_run_id=str(run_session.run_id) if run_session.run_id else None,
                        llm_call_id=llm_call_id,
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
                    await run_session.log_step("budget_snapshot", _build_budget_snapshot_payload(
                        owner_id=budget_owner_id,
                        reason="limit_exceeded",
                        step=step + 1,
                        policy=policy,
                        loop_state=loop_state,
                        start_time=loop_state.start_time,
                    ))
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
                if isinstance(runtime_budget, RunBudgetLedger):
                    loop_budget_snapshot = _build_budget_snapshot_payload(
                        owner_id=budget_owner_id,
                        reason="tool_call",
                        step=step + 1,
                        policy=policy,
                        loop_state=loop_state,
                        start_time=loop_state.start_time,
                    )
                    await run_session.log_step("budget_snapshot", loop_budget_snapshot)
                    yield RuntimeEvent(RuntimeEventType.BUDGET_SNAPSHOT, loop_budget_snapshot)

            # Max steps reached — synthesize with whatever we have
            if loop_state.operation_outputs:
                synth_final_content: List[str] = []
                async for ev in self._synthesize_answer(
                    exec_request, messages, loop_state.operation_outputs, loop_state.sources, gen, run_session,
                ):
                    if ev.type == RuntimeEventType.FINAL and isinstance(ev.data, dict):
                        synth_final_content.append(str(ev.data.get("content", "") or ""))
                    yield ev
                await run_session.log_step("final_response", {
                    "step": step + 1,
                    "operation_calls_total": len(loop_state.operation_outputs),
                    "content": synth_final_content[0] if synth_final_content else "",
                })
            else:
                yield RuntimeEvent.error(
                    f"Maximum agent steps ({policy.max_steps}) reached without result",
                    recoverable=True,
                    error_code=RuntimeErrorCode.AGENT_NO_SUCCESSFUL_OPERATION_RESULT,
                    retryable=True,
                )
            if isinstance(runtime_budget, RunBudgetLedger):
                final_budget_snapshot = _build_budget_snapshot_payload(
                    owner_id=budget_owner_id,
                    reason="final",
                    step=min(policy.max_steps, step + 1),
                    policy=policy,
                    loop_state=loop_state,
                    start_time=loop_state.start_time,
                )
                await run_session.log_step("budget_snapshot", final_budget_snapshot)
                yield RuntimeEvent(RuntimeEventType.BUDGET_SNAPSHOT, final_budget_snapshot)
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

    async def _resolve_llm_limits_for_agent(self, *, ctx: "ToolContext", agent_slug: str) -> ExecutionLimitsPayload:
        deps = ctx.get_runtime_deps()
        session_factory = deps.session_factory
        if session_factory is None:
            return ExecutionLimitsPayload()
        try:
            async with session_factory() as session:
                service = ExecutionLimitsService(session)
                base = await service.get_effective(
                    scope_type=ExecutionLimitScope.AGENT,
                    scope_ref=agent_slug,
                )
                sandbox_ov = deps.sandbox_overrides if isinstance(deps.sandbox_overrides, dict) else {}
                return apply_limits_override(base, sandbox_ov.get("agent_limits"))
        except Exception:
            return ExecutionLimitsPayload()

    async def _execute_single_operation_call(
        self,
        *,
        operation_call: Any,
        agent_slug: str,
        agent_run_id: Optional[str],
        llm_call_id: Optional[str],
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
            await run_session.log_step("budget_snapshot", {
                "owner_scope": "agent",
                "owner_id": agent_run_id,
                "parent_entity_type": "agent_run",
                "parent_entity_id": agent_run_id,
                "reason": "limit_exceeded",
                "snapshot": {
                    "tool_calls": {
                        "used": operation_calls_total_ref[0],
                        "limit": policy.max_tool_calls_total,
                        "remaining": 0,
                    },
                },
                "delta": {},
                "at_ms": int(time.time() * 1000),
            })
            await run_session.finish("failed", limit_message)
            return

        if isinstance(runtime_budget, RunBudgetLedger) and not runtime_budget.can_consume_tool_call():
            limit_message = (
                f"Maximum operation calls ({runtime_budget.budget.max_tool_calls_total}) reached"
            )
            yield RuntimeEvent.error(
                limit_message,
                recoverable=False,
                error_code=RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED,
                retryable=False,
            )
            await run_session.log_step("budget_snapshot", {
                "owner_scope": "agent",
                "owner_id": agent_run_id,
                "parent_entity_type": "agent_run",
                "parent_entity_id": agent_run_id,
                "reason": "limit_exceeded",
                "snapshot": {
                    "tool_calls": {
                        "used": runtime_budget.snapshot().get("consumed_tool_calls"),
                        "limit": runtime_budget.budget.max_tool_calls_total,
                        "remaining": 0,
                    },
                },
                "delta": {},
                "at_ms": int(time.time() * 1000),
            })
            await run_session.finish("failed", limit_message)
            return

        yield RuntimeEvent.operation_call(
            operation_call.operation_slug,
            operation_call.id,
            operation_call.arguments,
            agent_slug=agent_slug,
            agent_run_id=agent_run_id,
            llm_call_id=llm_call_id,
            parent_entity_type="agent_run",
            parent_entity_id=agent_run_id,
            actor_type="agent",
            actor_entity_id=agent_run_id,
        )
        await run_session.log_step("operation_call", {
            "operation_slug": operation_call.operation_slug,
            "call_id": operation_call.id,
            "arguments": operation_call.arguments,
            "input": operation_call.arguments,
            "agent_slug": agent_slug,
            "agent_run_id": agent_run_id,
            "llm_call_id": llm_call_id,
            "parent_entity_type": "agent_run",
            "parent_entity_id": agent_run_id,
            "actor_type": "agent",
            "actor_entity_id": agent_run_id,
        })

        try:
            result, sources = await self.tools.execute(
                operation_call, ctx, available_operations,
                timeout_s=(
                    int(
                        min(policy.tool_timeout_ms, runtime_budget.budget.per_tool_timeout_ms) / 1000
                    )
                    if policy.tool_timeout_ms and isinstance(runtime_budget, RunBudgetLedger)
                    else int(policy.tool_timeout_ms / 1000) if policy.tool_timeout_ms else None
                ),
            )
        except ConfirmationRequiredError as exc:
            yield RuntimeEvent(RuntimeEventType.CONFIRMATION_REQUIRED, dict(exc.payload))
            await run_session.finish("waiting_confirmation", str(exc))
            return

        consumed_tool_call = not bool(result.metadata.get("reused"))
        if consumed_tool_call:
            operation_calls_total_ref[0] += 1
            if isinstance(runtime_budget, RunBudgetLedger):
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
        operation_result_payload = RuntimeEvent.operation_result(
            operation_call.operation_slug,
            operation_call.id,
            result.success,
            sse_data,
            sources=sources if sources else None,
            agent_slug=agent_slug,
            agent_run_id=agent_run_id,
            llm_call_id=llm_call_id,
            parent_entity_type="agent_run",
            parent_entity_id=agent_run_id,
            actor_type="agent",
            actor_entity_id=agent_run_id,
            reused=bool(result.metadata.get("reused")),
            reused_from_call_id=result.metadata.get("reused_from_call_id"),
            error_code=raw_error_code,
            retryable=result.metadata.get("retryable"),
            safe_message=None if result.success else str(result.error or ""),
            envelope=envelope.to_metadata(),
            truncated=sse_truncated if sse_truncated else None,
        )
        yield operation_result_payload
        await run_session.log_step("operation_result", {
            "operation_slug": operation_call.operation_slug,
            "call_id": operation_call.id,
            "success": result.success,
            "reused": bool(result.metadata.get("reused")),
            "reused_from_call_id": result.metadata.get("reused_from_call_id"),
            "output": result.data if result.success else result.error,
            "result": result.data if result.success else result.error,
            "data": result.data if result.success else None,
            "error": None if result.success else str(result.error or ""),
            "safe_message": None if result.success else str(result.error or ""),
            "error_code": raw_error_code,
            "retryable": result.metadata.get("retryable"),
            "result_envelope": envelope.to_metadata(),
            "sources": list(sources or []),
            "agent_slug": agent_slug,
            "agent_run_id": agent_run_id,
            "llm_call_id": llm_call_id,
            "parent_entity_type": "agent_run",
            "parent_entity_id": agent_run_id,
            "actor_type": "agent",
            "actor_entity_id": agent_run_id,
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

    @staticmethod
    def _required_operation_retry_instruction(
        *,
        platform_config: Optional[Dict[str, Any]],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> str:
        runtime_override = None
        if isinstance(sandbox_overrides, dict):
            runtime_override = sandbox_overrides.get("required_operation_retry_instruction")
            if runtime_override is None and isinstance(sandbox_overrides.get("agent_runtime"), dict):
                runtime_override = sandbox_overrides["agent_runtime"].get(
                    "required_operation_retry_instruction"
                )
        if isinstance(runtime_override, str) and runtime_override.strip():
            return runtime_override.strip()

        policy_text = (platform_config or {}).get("retry_instruction")
        if isinstance(policy_text, str) and policy_text.strip():
            return policy_text.strip()
        return DEFAULT_REQUIRED_OPERATION_RETRY_INSTRUCTION

    @staticmethod
    def _intent_message(
        *,
        key: str,
        platform_config: Optional[Dict[str, Any]],
        sandbox_overrides: Optional[Dict[str, Any]],
        operation_slug: Optional[str] = None,
    ) -> str:
        templates = dict(DEFAULT_INTENT_MESSAGES)

        platform_templates = (platform_config or {}).get("intent_messages")
        if isinstance(platform_templates, dict):
            for template_key, template_value in platform_templates.items():
                if isinstance(template_value, str) and template_value.strip():
                    templates[str(template_key)] = template_value.strip()

        if isinstance(sandbox_overrides, dict):
            sandbox_templates = sandbox_overrides.get("intent_messages")
            if isinstance(sandbox_templates, dict):
                for template_key, template_value in sandbox_templates.items():
                    if isinstance(template_value, str) and template_value.strip():
                        templates[str(template_key)] = template_value.strip()

        template = templates.get(key) or DEFAULT_INTENT_MESSAGES.get(key, key)
        try:
            return template.format(operation_slug=operation_slug or "")
        except Exception:
            return template

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
