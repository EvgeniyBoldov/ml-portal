"""
AgentExecutor — adapter that runs a sub-agent via the existing AgentToolRuntime
and feeds its outcome back into WorkingMemory.

Design:
    * Pipeline → AgentExecutor.execute(step, memory, ...)
    * AgentExecutor builds a sub-ExecutionRequest via ExecutionPreflight (the
      sub-agent has its own policy/version/operations).
    * AgentToolRuntime runs the operation-call loop and emits legacy runtime
      events. We translate those to v3 events.
    * Sub-agent DELTAs and FINAL are captured into an AgentResult; they are
      NOT forwarded to the user — Synthesizer owns the final stream.
    * OPERATION_CALL / OPERATION_RESULT / STATUS pass through for observability.
    * ERROR events pass through and the agent_result is marked success=False.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.execution_preflight import ExecutionMode, ExecutionPreflight
from app.agents.runtime.agent import AgentToolRuntime
from app.agents.runtime.events import (
    RuntimeEvent as LegacyEvent,
    RuntimeEventType as LegacyEventType,
)
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.contracts import NextStep
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.memory.working_memory import AgentResult, WorkingMemory
from app.services.run_store import RunStore

logger = get_logger(__name__)


# Legacy -> v3 event-type mapping. Types absent from this map are dropped.
_PASS_THROUGH = {
    LegacyEventType.STATUS: RuntimeEventType.STATUS,
    LegacyEventType.OPERATION_CALL: RuntimeEventType.OPERATION_CALL,
    LegacyEventType.OPERATION_RESULT: RuntimeEventType.OPERATION_RESULT,
    LegacyEventType.ERROR: RuntimeEventType.ERROR,
}


class AgentExecutor:
    """Runs a single sub-agent step."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.run_store = run_store
        self.preflight = ExecutionPreflight(session)
        self._tool_runtime = AgentToolRuntime(
            llm_client=llm_client,
            run_store=run_store,
        )

    async def execute(
        self,
        *,
        step: NextStep,
        memory: WorkingMemory,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        agent_slug = step.agent_slug
        if not agent_slug:
            yield RuntimeEvent.error("AgentExecutor invoked without agent_slug")
            return

        # 1. Preflight for the sub-agent.
        try:
            sub_request = await self.preflight.prepare(
                agent_slug=agent_slug,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=(step.agent_input.get("query") or memory.goal)[:500],
                allow_partial=True,
                platform_config=platform_config,
                sandbox_overrides=sandbox_overrides,
                include_routable_agents=False,
            )
        except Exception as exc:
            logger.warning("Sub-agent preflight failed for %s: %s", agent_slug, exc)
            memory.add_agent_result(
                AgentResult(
                    agent_slug=agent_slug,
                    summary=f"preflight_failed: {exc}",
                    success=False,
                    error=str(exc),
                    iteration=memory.iter_count,
                    phase_id=step.phase_id,
                )
            )
            yield RuntimeEvent.status("sub_agent_unavailable", agent=agent_slug, error=str(exc))
            return

        if sub_request.mode == ExecutionMode.UNAVAILABLE:
            msg = "sub_agent_unavailable"
            memory.add_agent_result(
                AgentResult(
                    agent_slug=agent_slug,
                    summary=msg,
                    success=False,
                    error=msg,
                    iteration=memory.iter_count,
                    phase_id=step.phase_id,
                )
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        # 2. Compose the sub-agent's LLM messages. Goal + explicit agent_input.
        sub_messages = self._build_sub_messages(messages, step, memory)

        # 3. Run legacy AgentToolRuntime and translate events.
        buffered_answer: List[str] = []
        sub_sources: List[dict] = []
        final_content = ""
        final_error: Optional[str] = None
        success = True

        try:
            async for legacy in self._tool_runtime.execute(
                exec_request=sub_request,
                messages=sub_messages,
                ctx=ctx,
                model=model,
                enable_logging=True,
            ):
                translated = self._translate(legacy)
                if translated is not None:
                    yield translated

                if legacy.type == LegacyEventType.DELTA:
                    buffered_answer.append(str(legacy.data.get("content", "")))
                elif legacy.type == LegacyEventType.FINAL:
                    final_content = str(legacy.data.get("content", "") or "")
                    for src in legacy.data.get("sources") or []:
                        if isinstance(src, dict):
                            sub_sources.append(src)
                elif legacy.type == LegacyEventType.ERROR:
                    success = False
                    final_error = str(legacy.data.get("error", "") or "sub_agent_error")
        except Exception as exc:
            logger.error("Sub-agent execution failed: %s", exc, exc_info=True)
            success = False
            final_error = str(exc)
            yield RuntimeEvent.error(f"Sub-agent {agent_slug} failed: {exc}", recoverable=True)

        # 4. Summarize into AgentResult and enrich memory.
        raw_summary = final_content or "".join(buffered_answer)
        summary_preview = raw_summary.strip()[:800]
        facts = self._extract_facts(summary_preview, sub_sources)

        memory.used_tool_calls += self._count_operations(sub_request)
        memory.add_agent_result(
            AgentResult(
                agent_slug=agent_slug,
                summary=summary_preview or ("no_output" if success else (final_error or "failed")),
                facts=facts,
                phase_id=step.phase_id,
                iteration=memory.iter_count,
                success=success,
                error=final_error,
            )
        )

        # Expose sources to pipeline via memory_state for synthesizer.
        if sub_sources:
            current = list(memory.memory_state.get("sources") or [])
            current.extend(sub_sources)
            memory.memory_state["sources"] = current[:50]

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _translate(legacy: LegacyEvent) -> Optional[RuntimeEvent]:
        """Map legacy runtime events to v3. DELTA/FINAL are suppressed;
        THINKING collapses into STATUS; unknown types drop silently."""
        mapped = _PASS_THROUGH.get(legacy.type)
        if mapped is not None:
            return RuntimeEvent(mapped, dict(legacy.data))
        if legacy.type == LegacyEventType.THINKING:
            return RuntimeEvent.status("thinking", step=legacy.data.get("step"))
        # DELTA, FINAL, PLANNER_ACTION, POLICY_DECISION, WAITING_INPUT, STOP:
        # these are handled at pipeline level; don't leak.
        return None

    @staticmethod
    def _build_sub_messages(
        outer_messages: List[Dict[str, Any]],
        step: NextStep,
        memory: WorkingMemory,
    ) -> List[Dict[str, Any]]:
        """Compose sub-agent messages: inherit conversation context; pass planner's
        specific input as the last user turn."""
        query = step.agent_input.get("query") if step.agent_input else None
        if not query:
            query = memory.goal or (outer_messages[-1].get("content", "") if outer_messages else "")

        # Drop previous system messages (the sub-agent injects its own system prompt).
        non_system = [m for m in outer_messages if m.get("role") != "system"]
        # Replace last user message with the focused query for this sub-agent step.
        if non_system and non_system[-1].get("role") == "user":
            non_system = non_system[:-1]
        non_system.append({"role": "user", "content": str(query)})
        return non_system

    @staticmethod
    def _extract_facts(summary: str, sources: List[dict]) -> List[str]:
        """Very lightweight fact extraction. The planner prompt tells agents to
        return structured outputs, but we keep this defensive: one bullet-like
        fact per non-empty line, trimmed."""
        facts: List[str] = []
        for line in summary.splitlines():
            line = line.strip(" -*•\t")
            if not line:
                continue
            if len(line) < 8:
                continue
            facts.append(line[:280])
            if len(facts) >= 6:
                break
        for src in sources[:3]:
            title = (src.get("title") or src.get("name") or "").strip()
            if title:
                facts.append(f"source: {title[:120]}")
        return facts

    @staticmethod
    def _count_operations(exec_request: Any) -> int:
        return len(getattr(exec_request, "resolved_operations", []) or [])
