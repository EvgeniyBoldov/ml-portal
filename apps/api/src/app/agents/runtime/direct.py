"""
DirectRuntime — стриминг ответа LLM без tools и planner.

Используется когда:
- execution_mode == "direct"
- У агента нет привязанных tools
- Triage решил дать финальный ответ напрямую

Один LLM call, полный стриминг, минимальная латентность.
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from app.agents.runtime.base import BaseRuntime
from app.agents.runtime.events import RuntimeEvent
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.execution_limit import ExecutionLimitScope
from app.runtime.llm.limits import LLMLimitExceededError, apply_llm_limits, estimate_tokens
from app.services.execution_limits_service import ExecutionLimitsPayload, ExecutionLimitsService

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


class DirectRuntime(BaseRuntime):
    """Direct fast path — streaming LLM response without tools."""

    async def execute(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        agent = exec_request.agent

        # Resolve generation params via config
        gen = await self.config_resolver.resolve_direct(
            exec_request, ctx, model=model, temperature=temperature, max_tokens=max_tokens,
        )

        # Resolve system prompt through the shared prompt builder so sandbox
        # overrides and collection context stay on the same path as tool mode.
        sandbox_ov = ctx.get_runtime_deps().sandbox_overrides
        prompt_bundle = self.prompt_assembler.assemble(
            exec_request,
            system_prompt_override=system_prompt,
            sandbox_overrides=sandbox_ov,
        )

        # Build LLM messages
        llm_messages = [{"role": "system", "content": prompt_bundle.system_prompt}] + messages

        # Logging
        resolved_logging_level = await self.logging_resolver.resolve_logging_level(
            ctx,
            getattr(agent, "logging_level", None),
        )
        run_session = self._create_run_session(
            ctx=ctx,
            agent_slug=agent.slug,
            mode="direct",
            logging_level=resolved_logging_level.value,
            context_snapshot={"model": gen.model},
            enable_logging=enable_logging,
        )
        await run_session.start()

        yield RuntimeEvent.status("direct_streaming")

        logger.info(
            f"Direct path: agent={agent.slug}, model={gen.model}, "
            f"messages={len(llm_messages)}, max_tokens={gen.max_tokens}",
        )

        llm_call_id = f"{str(run_session.run_id)}:direct-llm:1" if run_session.run_id else str(uuid4())
        llm_limits = ExecutionLimitsPayload()
        runtime_deps = ctx.get_runtime_deps()
        session_factory = runtime_deps.session_factory or get_session_factory()
        if session_factory:
            async with session_factory() as session:
                llm_limits = await ExecutionLimitsService(session).get_effective(
                    scope_type=ExecutionLimitScope.AGENT,
                    scope_ref=str(getattr(agent, "slug", "") or "").strip() or None,
                )
        try:
            boundary = apply_llm_limits(
                limits=llm_limits,
                input_tokens=estimate_tokens(json.dumps(llm_messages, ensure_ascii=False, default=str)),
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

        full_content = ""
        llm_start = time.time()
        try:
            async for chunk in self.llm.stream(
                messages=llm_messages,
                model=gen.model,
                temperature=gen.temperature,
                max_tokens=effective_max_tokens,
            ):
                full_content += chunk
                yield RuntimeEvent.delta(chunk)

            llm_duration = int((time.time() - llm_start) * 1000)
            prompt_tokens = estimate_tokens(json.dumps(llm_messages, ensure_ascii=False, default=str))
            completion_tokens = estimate_tokens(full_content)
            total_tokens = prompt_tokens + completion_tokens

            await run_session.log_step("llm_turn", {
                "step": 1,
                "model": gen.model,
                "temperature": gen.temperature,
                "max_tokens": effective_max_tokens,
                "messages": llm_messages,
                "content": full_content,
                "response_length": len(full_content),
                "llm_call_id": llm_call_id,
                "parent_entity_type": "agent_run",
                "parent_entity_id": str(run_session.run_id) if run_session.run_id else None,
                "agent_run_id": str(run_session.run_id) if run_session.run_id else None,
                "agent_slug": agent.slug,
                "tokens_in": prompt_tokens,
                "tokens_out": completion_tokens,
                "tokens_total": total_tokens,
                "purpose": "direct_runtime_response",
                "actor_type": "direct",
                "actor_entity_id": str(run_session.run_id) if run_session.run_id else None,
            }, duration_ms=llm_duration, tokens_in=prompt_tokens, tokens_out=completion_tokens)
            yield RuntimeEvent.llm_turn(
                llm_call_id=llm_call_id,
                step=1,
                model=gen.model,
                temperature=gen.temperature,
                max_tokens=effective_max_tokens,
                messages=llm_messages,
                content=full_content,
                response_length=len(full_content),
                parent_entity_type="agent_run",
                parent_entity_id=str(run_session.run_id) if run_session.run_id else None,
                agent_run_id=str(run_session.run_id) if run_session.run_id else None,
                agent_slug=agent.slug,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                tokens_total=total_tokens,
                duration_ms=llm_duration,
                purpose="direct_runtime_response",
                actor_type="direct",
                actor_entity_id=str(run_session.run_id) if run_session.run_id else None,
            )

            yield RuntimeEvent.final(
                full_content,
                [],
                run_id=str(exec_request.run_id),
            )

            await run_session.log_step("direct_response", {
                "content_length": len(full_content),
                "model": gen.model,
            })
            await run_session.finish("completed")

        except Exception as e:
            logger.error(f"Direct streaming failed: {e}", exc_info=True)
            yield RuntimeEvent.error(str(e), recoverable=False)
            await run_session.finish("failed", str(e))
