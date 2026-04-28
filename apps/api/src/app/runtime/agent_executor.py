"""
AgentExecutor — adapter that runs a sub-agent via the existing AgentToolRuntime
and feeds its outcome back into RuntimeTurnState.

Design:
    * Pipeline → AgentExecutor.execute(step, runtime_state, ...)
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
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.agent import AgentToolRuntime
from app.agents.runtime.events import (
    RuntimeEvent as LegacyEvent,
    RuntimeEventType as LegacyEventType,
)
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.contracts import NextStep
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.memory.components import MemoryBundle, MemoryItem, MemorySection
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.turn_state import RuntimeTurnState
from app.services.run_store import RunStore

logger = get_logger(__name__)

MAX_SUB_AGENT_MESSAGES = 6
MAX_SUB_AGENT_MESSAGE_CHARS = 600
MAX_OPERATION_RESULT_PREVIEW_CHARS = 4096  # Limit payload size in SSE


# Legacy -> v3 event-type mapping. Types absent from this map are dropped.
_PASS_THROUGH = {
    LegacyEventType.STATUS: RuntimeEventType.STATUS,
    LegacyEventType.OPERATION_CALL: RuntimeEventType.OPERATION_CALL,
    LegacyEventType.OPERATION_RESULT: RuntimeEventType.OPERATION_RESULT,
    LegacyEventType.CONFIRMATION_REQUIRED: RuntimeEventType.CONFIRMATION_REQUIRED,
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
        # Shared executor instance per pipeline adapter to avoid per-step re-init churn.
        self._operation_executor = DirectOperationExecutor()

    async def execute(
        self,
        *,
        step: NextStep,
        runtime_state: RuntimeTurnState,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        agent_slug = step.agent_slug
        if not agent_slug:
            yield RuntimeEvent.error("AgentExecutor invoked without agent_slug")
            return
        state = runtime_state

        # 1. Preflight for the sub-agent.
        try:
            sub_request = await self.preflight.prepare(
                agent_slug=agent_slug,
                user_id=user_id,
                tenant_id=tenant_id,
                request_text=(step.agent_input.get("query") or state.goal)[:500],
                allow_partial=True,
                platform_config=platform_config,
                include_routable_agents=False,
            )
        except Exception as exc:
            logger.warning("Sub-agent preflight failed for %s: %s", agent_slug, exc)
            state.add_agent_result(
                {
                    "agent_slug": agent_slug,
                    "summary": f"preflight_failed: {exc}",
                    "success": False,
                    "error": str(exc),
                    "error_code": RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
                    "retryable": False,
                    "iteration": state.iter_count,
                    "phase_id": step.phase_id,
                }
            )
            yield RuntimeEvent.status("sub_agent_unavailable", agent=agent_slug, error=str(exc))
            return

        if sub_request.mode == ExecutionMode.UNAVAILABLE:
            msg = "sub_agent_unavailable"
            state.add_agent_result(
                {
                    "agent_slug": agent_slug,
                    "summary": msg,
                    "success": False,
                    "error": msg,
                    "error_code": RuntimeErrorCode.AGENT_UNAVAILABLE.value,
                    "retryable": False,
                    "iteration": state.iter_count,
                    "phase_id": step.phase_id,
                }
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        # Inject execution deps before any tool-runtime call.
        deps = ctx.get_runtime_deps()
        deps.operation_executor = deps.operation_executor or self._operation_executor
        deps.execution_graph = sub_request.execution_graph
        ctx.set_runtime_deps(deps)
        ctx.extra["runtime_tool_ledger"] = state.tool_ledger
        ctx.extra["runtime_tool_reuse_enabled"] = bool(
            (platform_config or {}).get("runtime_tool_reuse_enabled", True),
        )

        # Fast-path fallback: do not spend LLM calls when planner chose CALL_AGENT,
        # but the sub-agent ended up with zero executable operations.
        if not sub_request.resolved_operations:
            msg = "sub_agent_no_operations"
            state.add_agent_result(
                {
                    "agent_slug": agent_slug,
                    "summary": msg,
                    "success": False,
                    "error": msg,
                    "error_code": RuntimeErrorCode.AGENT_NO_OPERATIONS.value,
                    "retryable": False,
                    "iteration": state.iter_count,
                    "phase_id": step.phase_id,
                }
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        # 2. Compose the sub-agent's LLM messages. Goal + explicit agent_input.
        sub_messages = self._build_sub_messages(messages, step, state.goal)

        # 3. Run legacy AgentToolRuntime and translate events.
        buffered_answer: List[str] = []
        sub_sources: List[dict] = []
        final_content = ""
        final_error: Optional[str] = None
        final_error_code: Optional[str] = None
        final_retryable: Optional[bool] = None
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

                if legacy.type == LegacyEventType.OPERATION_CALL:
                    state.record_operation_call(
                        operation=str(legacy.data.get("operation") or ""),
                        call_id=str(legacy.data.get("call_id") or ""),
                        arguments=dict(legacy.data.get("arguments") or {}),
                        agent_slug=agent_slug,
                        phase_id=step.phase_id,
                    )
                elif legacy.type == LegacyEventType.OPERATION_RESULT:
                    result_payload = legacy.data.get("result")
                    if not isinstance(result_payload, dict):
                        result_payload = legacy.data.get("data")
                    state.record_operation_result(
                        call_id=str(legacy.data.get("call_id") or ""),
                        success=bool(legacy.data.get("success")),
                        data=result_payload,
                    )
                    if bool(legacy.data.get("reused")):
                        state.used_tool_calls = max(0, state.used_tool_calls - 1)

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
                    raw_code = legacy.data.get("error_code")
                    if raw_code is not None:
                        final_error_code = str(raw_code)
                    if "retryable" in legacy.data:
                        final_retryable = bool(legacy.data.get("retryable"))
                    elif "recoverable" in legacy.data:
                        final_retryable = bool(legacy.data.get("recoverable"))
        except Exception as exc:
            # NOTE(4.8): exc_info может содержать sensitive данные.
            # RuntimeRedactor применяется на уровне logging handler в проде.
            # Если ctx.extra содержит sensitive поля — они redacted перед traceback.
            logger.error("Sub-agent execution failed: %s", exc, exc_info=True)
            success = False
            final_error = str(exc)
            final_error_code = RuntimeErrorCode.AGENT_RUNTIME_EXCEPTION.value
            final_retryable = True
            yield RuntimeEvent.error(f"Sub-agent {agent_slug} failed: {exc}", recoverable=True)

        # 4. Summarize into AgentResult and enrich memory.
        raw_summary = final_content or "".join(buffered_answer)
        summary_preview = raw_summary.strip()[:800]
        facts = self._extract_facts(summary_preview, sub_sources)

        result_summary = summary_preview or ("no_output" if success else (final_error or "failed"))
        state.add_agent_result(
            {
                "agent_slug": agent_slug,
                "summary": result_summary,
                "facts": facts,
                "phase_id": step.phase_id,
                "iteration": state.iter_count,
                "success": success,
                "error": final_error,
                "error_code": final_error_code,
                "retryable": final_retryable,
            }
        )
        for fact in facts:
            state.add_runtime_fact(fact, source=agent_slug)

        # Store sources in runtime_state for synthesizer access
        if sub_sources:
            if not state.memory_bundle:
                state.memory_bundle = MemoryBundle(sections=[])
            # Find or create sources section
            sources_section = None
            for section in state.memory_bundle.sections:
                if section.name == "sources":
                    sources_section = section
                    break
            if sources_section is None:
                sources_section = MemorySection(name="sources", priority=90, items=[])
                state.memory_bundle.sections.append(sources_section)
            # Add new sources — src may be a dict; extract a text label for MemoryItem.
            existing_texts = {item.text for item in sources_section.items}
            for src in sub_sources:
                if isinstance(src, dict):
                    text = str(
                        src.get("title") or src.get("name") or src.get("url") or src
                    ).strip()
                else:
                    text = str(src).strip()
                if not text or text in existing_texts:
                    continue
                sources_section.items.append(MemoryItem(text=text, source="agent"))
                existing_texts.add(text)
            # Limit to 50
            sources_section.items = sources_section.items[-50:]

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _translate(legacy: LegacyEvent) -> Optional[RuntimeEvent]:
        """Map legacy runtime events to v3. DELTA/FINAL are suppressed;
        THINKING collapses into STATUS; unknown types drop silently."""
        mapped = _PASS_THROUGH.get(legacy.type)
        if mapped is not None:
            data = dict(legacy.data)
            # Limit OPERATION_RESULT payload size to prevent SSE leakage of large data
            if legacy.type == LegacyEventType.OPERATION_RESULT and "data" in data:
                payload = data["data"]
                if isinstance(payload, str) and len(payload) > MAX_OPERATION_RESULT_PREVIEW_CHARS:
                    data["data"] = payload[:MAX_OPERATION_RESULT_PREVIEW_CHARS] + "... [truncated]"
                    data["truncated"] = True
                elif isinstance(payload, (list, dict)):
                    try:
                        raw_str = __import__("json").dumps(payload, ensure_ascii=False, default=str)
                    except Exception:
                        raw_str = str(payload)
                    if len(raw_str) > MAX_OPERATION_RESULT_PREVIEW_CHARS:
                        data["data"] = raw_str[:MAX_OPERATION_RESULT_PREVIEW_CHARS] + "... [truncated]"
                        data["truncated"] = True
            return RuntimeEvent(mapped, data)
        if legacy.type == LegacyEventType.THINKING:
            return RuntimeEvent.status("thinking", step=legacy.data.get("step"))
        # DELTA, FINAL, PLANNER_ACTION, POLICY_DECISION, WAITING_INPUT, STOP:
        # these are handled at pipeline level; don't leak.
        return None

    @staticmethod
    def _build_sub_messages(
        outer_messages: List[Dict[str, Any]],
        step: NextStep,
        goal: str,
    ) -> List[Dict[str, Any]]:
        """Compose sub-agent messages: inherit conversation context; pass planner's
        specific input as the last user turn."""
        query = step.agent_input.get("query") if step.agent_input else None
        if not query:
            query = goal or (outer_messages[-1].get("content", "") if outer_messages else "")

        # Drop previous system messages (the sub-agent injects its own system prompt).
        # Keep only the latest bounded slice and trim message size to control token usage.
        non_system: List[Dict[str, Any]] = []
        for msg in outer_messages:
            if msg.get("role") == "system":
                continue
            role = str(msg.get("role") or "").strip()
            content = str(msg.get("content", "")).strip()
            if not role or not content:
                continue
            # Do not feed prior provider limit errors back into the sub-agent —
            # they create self-reinforcing prompt bloat and repeated failures.
            lowered = content.lower()
            if (
                "error code: 413" in lowered
                or "request too large" in lowered
                or "rate_limit_exceeded" in lowered
                or "tokens per minute" in lowered
            ):
                continue
            non_system.append(
                {
                    "role": role,
                    "content": content[:MAX_SUB_AGENT_MESSAGE_CHARS],
                }
            )
        non_system = non_system[-MAX_SUB_AGENT_MESSAGES:]
        # Replace last user message with the focused query for this sub-agent step.
        if non_system and non_system[-1].get("role") == "user":
            non_system = non_system[:-1]
        non_system.append({"role": "user", "content": str(query)})
        return non_system

    @staticmethod
    def _extract_facts(summary: str, sources: List[dict]) -> List[str]:
        """Lightweight fact extraction with markdown/JSON filtering.

        - JSON detection: if summary starts with '{', treat as single structured fact
        - Markdown filtering: skip table separators (|---|), headers (##), code blocks
        """
        facts: List[str] = []
        summary = (summary or "").strip()
        if not summary:
            return facts

        # JSON detection: structured output from sub-agent
        if summary.startswith("{"):
            facts.append(summary[:400])
            # Still append sources for context
            for src in sources[:3]:
                title = (src.get("title") or src.get("name") or "").strip()
                if title:
                    facts.append(f"source: {title[:120]}")
            return facts

        for line in summary.splitlines():
            line = line.strip(" -*•\t")
            if not line:
                continue
            # Skip markdown artifacts
            if line.startswith("##"):  # headers
                continue
            if line.startswith("|---"):  # table separators
                continue
            if line.startswith("```"):  # code blocks
                continue
            if line.startswith("|") and line.endswith("|"):  # table rows (keep content, strip pipes)
                line = line.strip("|").replace("|", " ")
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
