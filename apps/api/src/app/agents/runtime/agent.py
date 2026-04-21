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

import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.protocol import (
    build_operation_results_message,
    parse_llm_response,
)
from app.agents.runtime.tools import ConfirmationRequiredError
from app.agents.runtime.base import BaseRuntime
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


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

        yield RuntimeEvent.status("agent_operation_loop_started")

        # Build working messages for LLM (mutable copy)
        llm_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ] + list(messages)

        all_operation_outputs: List[Dict[str, Any]] = []
        all_sources: List[dict] = []
        start_time = time.time()
        operation_calls_total = 0

        try:
            for step in range(policy.max_steps):
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > policy.max_wall_time_ms:
                    yield RuntimeEvent.error("Wall time limit exceeded", recoverable=False)
                    await run_session.finish("failed", "Wall time limit exceeded")
                    return

                yield RuntimeEvent.thinking(step + 1)

                # Non-streaming LLM call to let agent decide
                llm_start = time.time()
                raw_response = await self.llm.call(
                    messages=llm_messages,
                    model=gen.model,
                    temperature=gen.temperature,
                    max_tokens=gen.max_tokens,
                )
                llm_duration = int((time.time() - llm_start) * 1000)

                await run_session.log_step("llm_call", {
                    "step": step + 1, "response_length": len(raw_response),
                }, duration_ms=llm_duration)

                # Parse operation calls from response
                strict_protocol = bool(platform_config.get("strict_operation_protocol", False))
                parsed = parse_llm_response(raw_response, strict=strict_protocol)

                if not parsed.has_operation_calls:
                    if available_operations and not all_operation_outputs:
                        if step + 1 >= policy.max_steps:
                            yield RuntimeEvent.error(
                                "Agent failed to call required operations before answering",
                                recoverable=False,
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
                        parsed, all_operation_outputs, all_sources, gen, run_session, sandbox_ov,
                    ):
                        yield ev
                    await run_session.log_step("final_response", {
                        "step": step + 1, "operation_calls_total": len(all_operation_outputs),
                    })
                    await run_session.finish("completed")
                    return

                # Execute each operation call
                operation_results_for_context: List[tuple] = []
                for operation_call in parsed.operation_calls:
                    if operation_calls_total >= policy.max_tool_calls_total:
                        limit_message = (
                            f"Maximum operation calls ({policy.max_tool_calls_total}) reached"
                        )
                        yield RuntimeEvent.error(limit_message, recoverable=False)
                        await run_session.log_step("budget_limit_exceeded", {
                            "kind": "max_tool_calls_total",
                            "limit": policy.max_tool_calls_total,
                            "consumed": operation_calls_total,
                        })
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
                            timeout_s=int(policy.tool_timeout_ms / 1000) if policy.tool_timeout_ms else None,
                        )
                    except ConfirmationRequiredError as exc:
                        yield RuntimeEvent(
                            RuntimeEventType.CONFIRMATION_REQUIRED,
                            dict(exc.payload),
                        )
                        await run_session.finish("waiting_confirmation", str(exc))
                        return
                    operation_calls_total += 1

                    yield RuntimeEvent.operation_result(
                        operation_call.operation_slug, operation_call.id, result.success,
                        result.data if result.success else result.error,
                    )

                    await run_session.log_step("operation_result", {
                        "operation_slug": operation_call.operation_slug,
                        "call_id": operation_call.id,
                        "success": result.success,
                        "output": result.data if result.success else result.error,
                        "result": result.data if result.success else result.error,
                    })

                    # Collect for synthesis
                    raw_output = result.data or {}
                    all_operation_outputs.append({
                        "operation": operation_call.operation_slug, "success": result.success,
                        "data": raw_output, "error": result.error,
                    })
                    all_sources.extend(sources)

                    result_text = self.tools.format_result_for_context(result)
                    operation_results_for_context.append((operation_call, result_text))

                # Add operation results to LLM context and loop back
                results_message = build_operation_results_message(operation_results_for_context)
                llm_messages.append({"role": "assistant", "content": raw_response})
                llm_messages.append({"role": "user", "content": results_message})

                logger.info(
                    f"Agent operation loop step={step + 1}: "
                    f"{len(parsed.operation_calls)} operation calls executed, "
                    f"total_outputs={len(all_operation_outputs)}",
                )

            # Max steps reached — synthesize with whatever we have
            if all_operation_outputs:
                async for ev in self._synthesize_answer(
                    exec_request, messages, all_operation_outputs, all_sources, gen, run_session,
                ):
                    yield ev
            else:
                yield RuntimeEvent.error(
                    f"Maximum agent steps ({policy.max_steps}) reached without result",
                    recoverable=True,
                )
            await run_session.finish("completed" if all_operation_outputs else "failed")

        except Exception as e:
            logger.error(f"Agent operation loop failed: {e}", exc_info=True)
            yield RuntimeEvent.error(str(e), recoverable=False)
            await run_session.finish("failed", str(e))

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
