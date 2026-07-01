"""
AgentExecutor — runs a sub-agent via the canonical tool runtime
and feeds its outcome back into RuntimeTurnState.

Design:
    * Pipeline → AgentExecutor.execute(step, runtime_state, ...)
    * AgentExecutor builds a sub-ExecutionRequest via ExecutionPreflight (the
      sub-agent has its own policy/version/operations).
    * AgentToolRuntime runs the tool-call loop and emits canonical runtime
      events directly.
    * Sub-agent DELTAs and FINAL are captured into an AgentResult; they are
      NOT forwarded to the user — Synthesizer owns the final stream.
    * TOOL_CALL / TOOL_RESULT / STATUS pass through for observability.
    * ERROR events pass through and the agent_result is marked success=False.
"""
from __future__ import annotations

from copy import deepcopy
import json
import traceback
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.execution_preflight import ExecutionMode, ExecutionPreflight
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.agent import AgentToolRuntime
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.contracts import AgentAnswerStatus, NeedSpec, NextStep
from app.runtime.context_snapshot import compact_snapshot
from app.agents.runtime.published_capabilities import (
    serialize_published_collections,
    serialize_published_operations,
)
from app.runtime.error_surface import build_user_safe_error_message
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.memory.components import MemoryBundle, MemoryItem, MemorySection
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.planner.iteration_policy import (
    resolve_agent_outcome,
    resolve_sufficient_for_phase,
)
from app.runtime.turn_state import RuntimeTurnState
from app.services.run_store import RunStore

logger = get_logger(__name__)

MAX_SUB_AGENT_MESSAGES = 6
MAX_SUB_AGENT_MESSAGE_CHARS = 600
MAX_OPERATION_RESULT_PREVIEW_CHARS = 4096  # Limit payload size in SSE


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
        lifecycle_agent_run_id: Optional[str] = None,
        runtime_state: RuntimeTurnState,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        agent_version_id: Optional[UUID] = None,
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
                agent_version_id=agent_version_id,
            )
        except Exception as exc:
            debug_traceback = traceback.format_exc()
            logger.warning("Sub-agent preflight failed for %s: %s", agent_slug, exc)
            state.add_agent_result(
                {
                    "agent_slug": agent_slug,
                    "summary": f"preflight_failed: {exc}",
                    "success": False,
                    "outcome": "failed",
                    "sufficient_for_phase": False,
                    "missing_inputs": [],
                    "error": str(exc),
                    "error_code": RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
                    "retryable": False,
                    "iteration": state.iter_count,
                    "phase_id": step.phase_id,
                    "debug": {
                        "exception_type": type(exc).__name__,
                        "traceback": debug_traceback,
                    },
                }
            )
            yield RuntimeEvent.error(
                f"Sub-agent {agent_slug} unavailable: {exc}",
                recoverable=False,
                error_code=RuntimeErrorCode.AGENT_PRECHECK_FAILED,
                retryable=False,
                stage="sub_agent_unavailable",
                agent=agent_slug,
                debug={
                    "exception_type": type(exc).__name__,
                    "traceback": debug_traceback,
                },
            )
            return

        if sub_request.mode == ExecutionMode.UNAVAILABLE:
            msg = "sub_agent_unavailable"
            state.add_agent_result(
                {
                    "agent_slug": agent_slug,
                    "summary": msg,
                    "success": False,
                    "outcome": "failed",
                    "sufficient_for_phase": False,
                    "missing_inputs": [],
                    "error": msg,
                    "error_code": RuntimeErrorCode.AGENT_UNAVAILABLE.value,
                    "retryable": False,
                    "iteration": state.iter_count,
                    "phase_id": step.phase_id,
                }
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        yield RuntimeEvent.status(
            "agent_context_snapshot",
            agent_slug=agent_slug,
            context_snapshot=self._build_context_snapshot(
                step=step,
                sub_request=sub_request,
                goal=state.goal,
                model=model,
            ),
        )

        # Inject execution deps before any tool-runtime call.
        deps = ctx.get_runtime_deps()
        deps.operation_executor = deps.operation_executor or self._operation_executor
        deps.execution_graph = sub_request.execution_graph
        deps.resolved_operations = list(sub_request.resolved_operations or [])
        ctx.set_runtime_deps(deps)
        if lifecycle_agent_run_id:
            ctx.extra["lifecycle_agent_run_id"] = lifecycle_agent_run_id
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
                    "outcome": "failed",
                    "sufficient_for_phase": False,
                    "missing_inputs": [],
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

        # 3. Run sub-agent tool loop and forward canonical runtime events.
        buffered_answer: List[str] = []
        sub_sources: List[dict] = []
        attachments: List[Dict[str, Any]] = []
        final_content = ""
        final_error: Optional[str] = None
        final_error_code: Optional[str] = None
        final_retryable: Optional[bool] = None
        success = True

        try:
            async for runtime_event in self._tool_runtime.execute(
                exec_request=sub_request,
                messages=sub_messages,
                ctx=ctx,
                model=model,
                enable_logging=True,
            ):
                yield runtime_event

                if runtime_event.type == RuntimeEventType.TOOL_CALL:
                    state.record_tool_call(
                        tool=str(runtime_event.data.get("tool") or ""),
                        call_id=str(runtime_event.data.get("call_id") or ""),
                        arguments=dict(runtime_event.data.get("arguments") or {}),
                        agent_slug=agent_slug,
                        phase_id=step.phase_id,
                    )
                elif runtime_event.type == RuntimeEventType.TOOL_RESULT:
                    result_payload = runtime_event.data.get("data")
                    state.record_tool_result(
                        call_id=str(runtime_event.data.get("call_id") or ""),
                        success=bool(runtime_event.data.get("success")),
                        data=result_payload,
                    )
                    if bool(runtime_event.data.get("reused")):
                        state.used_tool_calls = max(0, state.used_tool_calls - 1)

                    for src in runtime_event.data.get("sources") or []:
                        if isinstance(src, dict):
                            sub_sources.append(dict(src))

                    # Collect downloadable attachments for downstream synthesis
                    operation_name = str(runtime_event.data.get("tool") or "")
                    if operation_name in (
                        "file.generate",
                        "file_generate",
                        "collection.template.fill",
                        "instance.local-template-tools.collection.template.fill",
                    ) and bool(runtime_event.data.get("success")):
                        if isinstance(result_payload, dict):
                            file_id = result_payload.get("file_id")
                            if file_id:
                                download_url = result_payload.get("download_url") or f"/api/v1/files/{file_id}/download"
                                attachments.append({
                                    "file_id": file_id,
                                    "storage_uri": result_payload.get("storage_uri") or "",
                                    "file_name": result_payload.get("file_name") or result_payload.get("filename") or "file",
                                    "download_url": download_url,
                                    "content_type": result_payload.get("content_type") or "",
                                    "size_bytes": result_payload.get("size_bytes"),
                                })

                if runtime_event.type == RuntimeEventType.DELTA:
                    buffered_answer.append(str(runtime_event.data.get("content", "")))
                elif runtime_event.type == RuntimeEventType.FINAL:
                    final_content = str(runtime_event.data.get("content", "") or "")
                    for src in runtime_event.data.get("sources") or []:
                        if isinstance(src, dict):
                            sub_sources.append(src)
                elif runtime_event.type == RuntimeEventType.ERROR:
                    success = False
                    final_error = str(runtime_event.data.get("error", "") or "sub_agent_error")
                    raw_code = runtime_event.data.get("error_code")
                    if raw_code is not None:
                        final_error_code = str(raw_code)
                    if "retryable" in runtime_event.data:
                        final_retryable = bool(runtime_event.data.get("retryable"))
                    elif "recoverable" in runtime_event.data:
                        final_retryable = bool(runtime_event.data.get("recoverable"))
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

        # Parse structured needs from agent output if present
        needs = self._parse_needs_from_content(raw_summary)
        missing_inputs = [n.key for n in needs]

        # Determine status/completion_kind based on success and needs
        if not success:
            status = AgentAnswerStatus.FAILED
            completion_kind = "error"
        elif needs:
            status = AgentAnswerStatus.NEEDS_INPUT
            completion_kind = "paused_need"
        else:
            status = AgentAnswerStatus.COMPLETE
            completion_kind = "answered"

        # Invariant: paused_need never closes a phase — planner must route needs
        sufficient_for_phase = (
            False
            if status == AgentAnswerStatus.NEEDS_INPUT
            else resolve_sufficient_for_phase(
                success=success,
                summary=summary_preview,
                missing_inputs=missing_inputs,
            )
        )

        outcome = resolve_agent_outcome(success=success)
        result_summary = summary_preview or ("no_output" if success else (final_error or "failed"))

        state.add_agent_result(
            {
                "agent_slug": agent_slug,
                "summary": result_summary,
                "facts": facts,
                "phase_id": step.phase_id,
                "iteration": state.iter_count,
                "success": success,
                "outcome": outcome,
                "status": status.value,
                "completion_kind": completion_kind,
                "sufficient_for_phase": sufficient_for_phase,
                "missing_inputs": missing_inputs,
                "needs": [n.model_dump() for n in needs],
                "error": final_error,
                "error_code": final_error_code,
                "retryable": final_retryable,
                "user_safe_error": (
                    build_user_safe_error_message(
                        retryable=final_retryable,
                        error_code=final_error_code,
                    )
                    if not success
                    else None
                ),
                "attachments": attachments,
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
                source_metadata = {"source": dict(src)} if isinstance(src, dict) else {}
                sources_section.items.append(MemoryItem(text=text, source="agent", metadata=source_metadata))
                existing_texts.add(text)
            # Limit to 50
            sources_section.items = sources_section.items[-50:]

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _build_sub_messages(
        outer_messages: List[Dict[str, Any]],
        step: NextStep,
        goal: str,
    ) -> List[Dict[str, Any]]:
        """Compose sub-agent messages: inherit conversation context; pass planner's
        specific input as the last user turn.

        For recall calls (dozvon) injects resolved_needs and prior_summary from
        agent_input so the agent can continue its task with fresh data."""
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

        # Build the final user message: inject recall context if present
        parts: List[str] = []
        if step.agent_input:
            prior_summary = step.agent_input.get("prior_summary")
            if prior_summary:
                parts.append(f"[Previous work summary]\n{prior_summary}")
            resolved_needs = step.agent_input.get("resolved_needs")
            if isinstance(resolved_needs, list) and resolved_needs:
                parts.append("[Resolved needs]")
                for rn in resolved_needs:
                    if isinstance(rn, dict):
                        parts.append(f"- {rn.get('key')}: {rn.get('value')}")
        if parts:
            parts.append(f"[Task]\n{query}")
            final_query = "\n\n".join(parts)
        else:
            final_query = str(query)

        non_system.append({"role": "user", "content": final_query})
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

    @staticmethod
    def _parse_needs_from_content(raw: str) -> List[NeedSpec]:
        """Extract structured needs from agent output.

        Supports two shapes:
        - Top-level JSON with a 'needs' array: {"status": "needs_input", "needs": [{"ref": "...", "key": "...", "description": "..."}]}
        - Inline JSON block inside markdown code fences.
        Returns empty list if no structured needs found.
        """
        text = (raw or "").strip()
        if not text:
            return []
        # Try to find a JSON object containing 'needs' anywhere in the text
        # Strategy: look for the last JSON block (agent typically puts structured
        # output at the end) and validate it.
        try:
            # If the entire text is JSON
            if text.startswith("{"):
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return AgentExecutor._extract_needs_from_dict(parsed)
        except Exception:
            pass
        # Try extracting from markdown code fence
        code_fence_match = None
        if "```json" in text:
            parts = text.split("```json")
            if len(parts) > 1:
                code_fence_match = parts[-1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) > 1:
                code_fence_match = parts[-1].split("```")[0].strip()
        if code_fence_match:
            try:
                parsed = json.loads(code_fence_match)
                if isinstance(parsed, dict):
                    return AgentExecutor._extract_needs_from_dict(parsed)
            except Exception:
                pass
        return []

    @staticmethod
    def _extract_needs_from_dict(parsed: Dict[str, Any]) -> List[NeedSpec]:
        needs_data = parsed.get("needs")
        if not isinstance(needs_data, list):
            return []
        result: List[NeedSpec] = []
        for item in needs_data:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            result.append(
                NeedSpec(
                    ref=str(item.get("ref") or key),
                    kind=str(item.get("kind") or "data"),
                    key=key,
                    description=str(item.get("description") or "").strip() or key,
                    context=dict(item.get("context") or {}),
                )
            )
        return result

    @staticmethod
    def _build_context_snapshot(
        *,
        step: NextStep,
        sub_request: ExecutionRequest,
        goal: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        collection_filter_audit = (sub_request.rbac_audit or {}).get("collection_filter")
        version_label: Optional[str] = None
        version = sub_request.agent_version
        if version is not None:
            version_number = getattr(version, "version", None)
            version_status = getattr(version, "status", None)
            if version_number is not None:
                version_label = f"v{version_number}"
                if version_status:
                    version_label = f"{version_label} ({version_status})"

        return compact_snapshot(
            inputs={
                "goal": goal,
                "agent_input": step.agent_input or {},
            },
            prompt={"system_prompt": sub_request.prompt} if sub_request.prompt else None,
            rbac=deepcopy(collection_filter_audit) if isinstance(collection_filter_audit, dict) else None,
            meta={
                "role": sub_request.agent_slug,
                "agent_slug": sub_request.agent_slug,
                "model": model or getattr(sub_request.agent, "model", None),
                "version_label": version_label,
                "available_operations": serialize_published_operations(sub_request.resolved_operations or []),
                "available_collections": serialize_published_collections(
                    sub_request.resolved_data_instances or [],
                    sub_request.resolved_operations or [],
                ),
            },
        ) or {}
