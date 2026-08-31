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

import asyncio
from copy import deepcopy
import json
import re
import traceback
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.execution_preflight import ExecutionMode, ExecutionPreflight
from app.core.config import get_settings
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.agent import AgentToolRuntime
from app.agents.operation_publication import PUBLIC_RETRIEVAL_OPERATIONS
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.contracts import NeedSpec
from app.runtime.orchestrator_contracts import (
    AgentExecutionResult,
    AgentTaskResult,
    TaskConfirmationRequired,
    TaskExecutionError,
    TaskRequest,
    parse_agent_execution_result,
)
from app.runtime.context_snapshot import compact_snapshot
from app.runtime.error_payloads import build_debug_payload
from app.agents.runtime.published_capabilities import (
    serialize_published_collections,
    serialize_published_operations,
)
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.events import OrchestrationPhase
from app.runtime.memory.components import MemoryBundle, MemoryItem, MemorySection
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.turn_state import RuntimeTurnState

logger = get_logger(__name__)

MAX_SUB_AGENT_MESSAGES = 6
MAX_SUB_AGENT_MESSAGE_CHARS = 600
MAX_OPERATION_RESULT_PREVIEW_CHARS = 4096  # Limit payload size in SSE


class AgentExecutor:
    """Runs one persisted graph task through the canonical agent runtime."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.preflight = ExecutionPreflight(session)
        self._tool_runtime = AgentToolRuntime(
            llm_client=llm_client,
        )
        # Shared executor instance per pipeline adapter to avoid per-step re-init churn.
        self._operation_executor = DirectOperationExecutor()

    async def execute(
        self,
        *,
        task: TaskRequest,
        lifecycle_agent_execution_id: Optional[str] = None,
        runtime_state: RuntimeTurnState,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        agent_version_id: Optional[UUID] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        agent_slug = task.executor
        if not agent_slug:
            yield RuntimeEvent.error(
                "AgentExecutor invoked without agent_slug",
                recoverable=False,
                user_message="AgentExecutor invoked without agent_slug",
                operator_message="AgentExecutor invoked without agent_slug",
                source="runtime",
            )
            return
        state = runtime_state

        # 1. Preflight for the sub-agent.
        preflight_timeout_s = get_settings().PREFLIGHT_TIMEOUT_SECONDS
        try:
            sub_request = await asyncio.wait_for(
                self.preflight.prepare(
                    agent_slug=agent_slug,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    request_text=str(task.inputs.get("query") or task.instructions or state.goal)[:500],
                    allow_partial=True,
                    platform_config=platform_config,
                    include_routable_agents=False,
                    agent_version_id=agent_version_id,
                    event_sink=ctx.extra.get("runtime_event_logger"),
                    trace_parent_id=lifecycle_agent_execution_id,
                ),
                timeout=preflight_timeout_s,
            )
        except Exception as exc:
            debug_traceback = traceback.format_exc()
            error_message = (
                f"Preflight timed out after {preflight_timeout_s}s"
                if isinstance(exc, asyncio.TimeoutError)
                else str(exc)
            )
            logger.warning("Sub-agent preflight failed for %s: %s", agent_slug, error_message)
            ctx.extra["agent_execution_failure"] = {
                "code": RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
                "message": error_message,
                "retryable": False,
            }
            yield RuntimeEvent.error(
                f"Sub-agent {agent_slug} unavailable: {error_message}",
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
            ctx.extra["agent_execution_result"] = AgentExecutionResult(
                completion="unfulfillable",
                description=msg,
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        yield RuntimeEvent.status(
            "agent_context_snapshot",
            agent_slug=agent_slug,
            context_snapshot=self._build_context_snapshot(
                task=task,
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
        if lifecycle_agent_execution_id:
            ctx.extra["lifecycle_agent_execution_id"] = lifecycle_agent_execution_id
        ctx.extra["runtime_tool_ledger"] = state.tool_ledger
        ctx.extra["runtime_turn_state"] = state
        ctx.extra["runtime_tool_reuse_enabled"] = bool(
            (platform_config or {}).get("runtime_tool_reuse_enabled", True),
        )
        ctx.extra["task_freshness_policy"] = task.freshness_policy.value
        ctx.extra["task_freshness_phase_id"] = task.task_id
        ledger_start = len(state.tool_ledger.entries)

        # Fast-path fallback: do not spend LLM calls when planner chose CALL_AGENT,
        # but the sub-agent ended up with zero executable operations.
        if not sub_request.resolved_operations and task.freshness_policy.value == "allow_memory":
            # No operations is not an execution error for a reasoning task.
            # The normal model path below can still return a bounded answer.
            pass
        elif not sub_request.resolved_operations:
            msg = "sub_agent_no_operations"
            ctx.extra["agent_execution_result"] = AgentExecutionResult(
                completion="unfulfillable",
                description=msg,
            )
            yield RuntimeEvent.status(msg, agent=agent_slug)
            return

        # 2. Compose the sub-agent's LLM messages. Goal + explicit agent_input.
        sub_messages = self._build_sub_messages(
            messages,
            task,
            state.goal,
            [item.model_dump(mode="json") for item in (state.attachment_contexts or [])],
        )

        # 3. Run sub-agent tool loop and forward canonical runtime events.
        buffered_answer: List[str] = []
        sub_sources: List[dict] = []
        attachments: List[Dict[str, Any]] = []
        artifacts: List[Dict[str, Any]] = []
        final_content = ""
        final_error: Optional[str] = None
        final_error_code: Optional[str] = None
        final_retryable: Optional[bool] = None
        final_retry_after_ms: Optional[int] = None
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
                        phase_id=task.task_id,
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

                    if bool(runtime_event.data.get("success")):
                        artifacts.extend(self._extract_artifacts(result_payload))

                    # Collect downloadable attachments for downstream synthesis
                    operation_name = str(runtime_event.data.get("tool") or "")
                    if (
                        operation_name in ("file.delete", "file_delete")
                        and bool(runtime_event.data.get("success"))
                        and isinstance(result_payload, dict)
                    ):
                        state.mark_artifact_deleted(str(result_payload.get("artifact_id") or ""))
                    if self._creates_downloadable_artifact(operation_name) and bool(runtime_event.data.get("success")):
                        if isinstance(result_payload, dict):
                            artifact_id = result_payload.get("artifact_id")
                            if artifact_id:
                                attachments.append({
                                    "artifact_id": artifact_id,
                                    "file_name": result_payload.get("file_name") or result_payload.get("filename") or "file",
                                    "download_url": f"/api/v1/files/{artifact_id}/download",
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
                    raw_retry_after_ms = runtime_event.data.get("retry_after_ms")
                    if isinstance(raw_retry_after_ms, int) and raw_retry_after_ms > 0:
                        final_retry_after_ms = raw_retry_after_ms
        except Exception as exc:
            # NOTE(4.8): exc_info может содержать sensitive данные.
            # RuntimeRedactor применяется на уровне logging handler в проде.
            # Если ctx.extra содержит sensitive поля — они redacted перед traceback.
            logger.error("Sub-agent execution failed: %s", exc, exc_info=True)
            success = False
            final_error = str(exc)
            final_error_code = RuntimeErrorCode.AGENT_RUNTIME_EXCEPTION.value
            final_retryable = True
            yield RuntimeEvent.error(
                f"Sub-agent {agent_slug} failed: {exc}",
                recoverable=True,
                error_code=RuntimeErrorCode.AGENT_RUNTIME_EXCEPTION,
                retryable=True,
                user_message=f"Sub-agent {agent_slug} failed: {exc}",
                operator_message=str(exc),
                source="runtime",
                debug=build_debug_payload(exc=exc),
            )

        # 4. Normalize the terminal task contract.  Agent prose is not an
        # implicit task result: graph tasks must end with strict JSON.
        raw_summary = final_content or "".join(buffered_answer)
        if not success:
            ctx.extra["agent_execution_failure"] = {
                "code": final_error_code or "agent_failed",
                "message": final_error or "Task execution failed",
                "retryable": bool(final_retryable),
                "retry_after_ms": final_retry_after_ms,
            }
        else:
            try:
                execution = parse_agent_execution_result(raw_summary)
            except ValueError as exc:
                ctx.extra["agent_execution_failure"] = {
                    "code": "agent_task_completion_invalid",
                    "message": str(exc),
                    "retryable": True,
                }
            else:
                verified = self._verified_task_result(
                    task=task,
                    ledger_entries=state.tool_ledger.entries[ledger_start:],
                )
                ctx.extra["agent_execution_result"] = execution.model_copy(
                    update={"verified": verified, "receipt_refs": list(verified.get("receipts") or [])}
                )

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

    async def execute_attempt(
        self,
        *,
        request: TaskRequest,
        runtime_state: RuntimeTurnState,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        platform_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        agent_version_id: Optional[UUID] = None,
        lifecycle_agent_execution_id: Optional[str] = None,
        runtime_log_parent: Optional[Dict[str, str]] = None,
        **_: Any,
    ) -> AgentExecutionResult:
        """Consume one executor stream and return its normalized result.

        Every agent event is persisted by the root sink before the graph turns
        the terminal result into a state transition.
        """
        confirmation_payload: Optional[Dict[str, Any]] = None
        logger = ctx.extra.get("runtime_event_logger") if isinstance(ctx.extra, dict) else None
        if runtime_log_parent:
            ctx.extra["runtime_log_parent"] = dict(runtime_log_parent)
        async for event in self.execute(
            task=request,
            lifecycle_agent_execution_id=lifecycle_agent_execution_id,
            runtime_state=runtime_state,
            messages=messages,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            platform_config=platform_config,
            model=model,
            agent_version_id=agent_version_id,
        ):
            if event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
                confirmation_payload = dict(event.data or {})
            if logger is not None:
                # The graph owns the task pause and emits the canonical
                # interaction event with its persisted checkpoint.
                if event.type != RuntimeEventType.CONFIRMATION_REQUIRED:
                    await logger.emit(event, phase=OrchestrationPhase.AGENT)
        if confirmation_payload is not None:
            raise TaskConfirmationRequired(confirmation_payload)
        failure = ctx.extra.pop("agent_execution_failure", None)
        if isinstance(failure, dict):
            retry_after_ms = failure.get("retry_after_ms")
            raise TaskExecutionError(
                code=str(failure.get("code") or "agent_failed"),
                message=str(failure.get("message") or "Task execution failed"),
                retryable=bool(failure.get("retryable")),
                details={"retry_after_ms": retry_after_ms}
                if isinstance(retry_after_ms, int) and retry_after_ms > 0 else {},
            )
        execution = ctx.extra.pop("agent_execution_result", None)
        if not isinstance(execution, AgentExecutionResult):
            raise TaskExecutionError(
                code="agent_task_completion_missing",
                message="Agent did not return a terminal task completion",
                retryable=True,
            )
        return execution

    async def execute_task(self, **kwargs: Any) -> AgentTaskResult:
        """Compatibility adapter for legacy direct task-executor callers."""
        from app.runtime.task_result_reducer import TaskAttemptResultReducer

        request = kwargs["request"]
        execution = await self.execute_attempt(**kwargs)
        return TaskAttemptResultReducer().reduce(request=request, execution=execution)

    @staticmethod
    def _verified_task_result(*, task: TaskRequest, ledger_entries: List[Any]) -> Dict[str, Any]:
        """Project only receipts observed by runtime during this attempt."""
        receipts: List[Dict[str, Any]] = []
        evidence: Dict[str, Any] = {}
        artifacts: List[Dict[str, Any]] = []
        memory_candidates: List[Dict[str, Any]] = []
        fresh_retrieval = False
        for entry in ledger_entries:
            if getattr(entry, "status", None) != "succeeded" or not getattr(entry, "success", False):
                continue
            operation = str(getattr(entry, "operation", "") or "")
            normalized = operation.removeprefix("instance.").split(".", 1)[-1] if operation.startswith("instance.") else operation
            is_retrieval = normalized in PUBLIC_RETRIEVAL_OPERATIONS
            fresh_retrieval = fresh_retrieval or is_retrieval
            receipt = {
                "call_id": str(getattr(entry, "call_id", "")),
                "operation": operation,
                "result_fingerprint": getattr(entry, "result_fingerprint", None),
                "result_preview": getattr(entry, "result_preview", None),
                "retrieval": is_retrieval,
            }
            receipts.append(receipt)
            evidence[receipt["call_id"]] = {"operation": operation, "result_fingerprint": receipt["result_fingerprint"]}
            artifacts.extend(AgentExecutor._extract_artifacts(getattr(entry, "result_data", None)))
            if normalized in {"project_memory.mark", "memory.mark"}:
                memory_candidates.append({
                    "call_id": receipt["call_id"],
                    "result_fingerprint": receipt["result_fingerprint"],
                    "status": "accepted_candidate",
                })
        artifacts = AgentExecutor._dedupe_artifacts(artifacts)
        return {
            "status": "observed",
            "fresh_retrieval": fresh_retrieval,
            "receipts": receipts,
            "evidence": evidence,
            "artifacts": artifacts,
            "memory_candidates": memory_candidates,
        }

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _creates_downloadable_artifact(operation_name: str) -> bool:
        """Whether a canonical operation result represents a newly created file."""
        normalized = str(operation_name or "").strip()
        return normalized in {"file.generate", "file_generate", "collection.template.fill"} or (
            normalized.endswith(".file.generate")
            or normalized.endswith(".collection.template.fill")
        )

    @staticmethod
    def _is_url_only_response(content: str) -> bool:
        """Detect an artifact-only agent response without trusting its URL."""
        return bool(re.fullmatch(r"https?://[^\r\n]+", str(content or "").strip().strip("`")))

    @staticmethod
    def _extract_artifacts(payload: Any, *, limit: int = 20) -> List[Dict[str, Any]]:
        """Extract safe opaque file references from successful tool output."""
        result: List[Dict[str, Any]] = []

        def visit(value: Any) -> None:
            if len(result) >= limit:
                return
            if isinstance(value, dict):
                artifact_id = str(value.get("artifact_id") or "").strip()
                if artifact_id:
                    result.append({
                        "artifact_id": artifact_id,
                        "file_name": value.get("file_name") or value.get("filename") or value.get("name") or value.get("title") or "artifact",
                        "content_type": value.get("content_type"),
                        "size_bytes": value.get("size_bytes"),
                    })
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        return AgentExecutor._dedupe_artifacts(result)[:limit]

    @staticmethod
    def _dedupe_artifacts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        return [
            item for item in items
            if isinstance(item, dict)
            and (artifact_id := str(item.get("artifact_id") or "").strip())
            and not (artifact_id in seen or seen.add(artifact_id))
        ]

    @staticmethod
    def _build_sub_messages(
        outer_messages: List[Dict[str, Any]],
        task: TaskRequest,
        goal: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Compose sub-agent messages: inherit conversation context; pass planner's
        specific input as the last user turn.

        For recall calls (dozvon) injects resolved_needs and prior_summary from
        agent_input so the agent can continue its task with fresh data."""
        query = task.inputs.get("query") or task.instructions
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
        if task.inputs:
            prior_summary = task.inputs.get("prior_summary")
            if prior_summary:
                parts.append(f"[Previous work summary]\n{prior_summary}")
            resolved_needs = task.inputs.get("resolved_needs")
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

        if task.dependency_outputs:
            dependency_lines = ["[Dependency outputs]"]
            remaining = 8000
            for task_id, output in list(task.dependency_outputs.items())[:8]:
                if not isinstance(output, dict):
                    continue
                projection = {
                    "outcome": output.get("outcome"),
                    "status": output.get("status"),
                    "description": str(output.get("description") or "")[:1200],
                    "outputs": output.get("outputs") or {},
                    "receipts": list(output.get("verified_receipts") or [])[:8],
                    "evidence": output.get("verified_evidence") or {},
                    "artifacts": list(output.get("artifacts") or [])[:8],
                }
                try:
                    rendered = json.dumps(projection, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    rendered = str(projection).strip()
                if rendered:
                    rendered = rendered[: min(4000, remaining)]
                    dependency_lines.append(f"- {task_id}: {rendered}")
                    remaining -= len(rendered)
                    if remaining <= 0:
                        break
            if len(dependency_lines) > 1:
                final_query = "\n\n".join(["\n".join(dependency_lines), final_query])

        if task.memory_context:
            memory_lines = ["[Relevant durable memory]"]
            for item in task.memory_context[:12]:
                if not isinstance(item, dict):
                    continue
                subject = str(item.get("subject") or "").strip()
                value = str(item.get("value") or "").strip()
                if subject and value:
                    memory_lines.append(f"- [{item.get('scope', 'memory')}] {subject}: {value}")
            if len(memory_lines) > 1:
                final_query = "\n\n".join(["\n".join(memory_lines), final_query])

        attachment_items = list(attachments or [])
        for dependency in task.dependency_outputs.values():
            if not isinstance(dependency, dict):
                continue
            for artifact in dependency.get("artifacts") or []:
                if isinstance(artifact, dict) and artifact.get("artifact_id"):
                    attachment_items.append({
                        "ref": {
                            "artifact_id": artifact.get("artifact_id"),
                            "file_name": artifact.get("file_name") or artifact.get("name") or "artifact",
                        },
                        "snippet_status": artifact.get("snippet_status") or "missing",
                        "snippet": artifact.get("snippet") or "",
                    })
        if attachment_items:
            attachment_lines = ["[Available attachments]"]
            for item in attachment_items:
                if not isinstance(item, dict):
                    continue
                ref = item.get("ref") if isinstance(item.get("ref"), dict) else {}
                file_name = str(ref.get("file_name") or "file").strip()
                artifact_id = str(ref.get("artifact_id") or "").strip()
                snippet_status = str(item.get("snippet_status") or "missing").strip()
                snippet = str(item.get("snippet") or "").strip()
                attachment_lines.append(
                    f"- {file_name} (artifact_id={artifact_id}; snippet_status={snippet_status})"
                )
                if snippet:
                    attachment_lines.append(snippet)
            if len(attachment_lines) > 1:
                final_query = "\n\n".join(["\n".join(attachment_lines), final_query])

        output_contract = [
            "[Terminal task completion contract]",
            "After work, return exactly one JSON object and no prose or markdown.",
            "Required fields: completion (fulfilled|needs|unfulfillable), description, needs (array), outputs (object), checkpoint (object).",
            "Each outputs key contains text, data, and/or artifacts. Use needs=[] when fulfilled or unfulfillable.",
        ]
        if task.expected_outputs:
            output_contract.append("Expected output keys: " + ", ".join(
                f"{item.key} ({item.fulfillment.value})" for item in task.expected_outputs
            ))
        final_query = "\n\n".join(["\n".join(output_contract), final_query])

        non_system.append({"role": "user", "content": final_query})
        return non_system

    @staticmethod
    def _parse_structured_response(raw: str) -> Dict[str, Any]:
        """Read the bounded agent result envelope without treating prose as data."""
        text = (raw or "").strip()
        candidates = [text]
        if "```json" in text:
            candidates.append(text.split("```json", 1)[1].split("```", 1)[0].strip())
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

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
        task: TaskRequest,
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
                "task_id": task.task_id,
                "intent": task.intent,
                "instructions": task.instructions,
                "inputs": task.inputs,
                "dependency_outputs": task.dependency_outputs,
                "needs": [need.model_dump(mode="json", by_alias=True) for need in task.needs],
            },
            prompt={"system_prompt": sub_request.prompt} if sub_request.prompt else None,
            rbac=deepcopy(collection_filter_audit) if isinstance(collection_filter_audit, dict) else None,
            meta={
                "role": sub_request.agent_slug,
                "agent_slug": sub_request.agent_slug,
                "model": model or getattr(sub_request.agent, "model", None),
                "version_label": version_label,
                "execution_mode": sub_request.mode.value,
                "available_operations": serialize_published_operations(sub_request.resolved_operations or []),
                "available_collections": serialize_published_collections(
                    sub_request.resolved_data_instances or [],
                    sub_request.resolved_operations or [],
                ),
            },
        ) or {}
