"""
DirectRuntime — стриминг ответа LLM без tools и planner.

Используется когда:
- execution_mode == "direct"
- У агента нет привязанных tools
- Triage решил дать финальный ответ напрямую

Один LLM call, полный стриминг, минимальная латентность.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.runtime.base import BaseRuntime
from app.agents.runtime.events import RuntimeEvent
from app.core.logging import get_logger

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

        full_content = ""
        try:
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
