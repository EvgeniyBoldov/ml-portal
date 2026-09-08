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
from app.adapters.s3_client import s3_manager
from app.core.logging import get_logger
from app.runtime.orchestrator_contracts import (
    TaskCompletionDeclaration,
    TaskExecutionReceipt,
    DiscoveredNeed,
    TaskConfirmationRequired,
    TaskExecutionError,
    TaskRequest,
    parse_task_completion_declaration,
    task_completion_json_schema,
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
from app.runtime.result_store import RuntimeToolResultStore

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
        runtime_plan_id: Optional[str] = None,
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
                    request_text=str(task.instructions or state.goal)[:500],
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
            ctx.extra["agent_execution_result"] = TaskCompletionDeclaration(
                completion="unfulfillable",
                report=msg,
                limitation={"code": msg, "message": "The selected agent is unavailable.", "action": "none"},
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
        ctx.extra["runtime_result_store"] = RuntimeToolResultStore(self.session)
        ctx.extra["runtime_plan_id"] = runtime_plan_id
        ctx.extra["runtime_task_id"] = task.task_id
        ctx.extra["runtime_turn_state"] = state
        ctx.extra["runtime_tool_reuse_enabled"] = bool(
            (platform_config or {}).get("runtime_tool_reuse_enabled", True),
        )
        ctx.extra["task_freshness_policy"] = task.freshness_policy.value
        ctx.extra["task_freshness_phase_id"] = task.task_id
        ledger_start = len(state.tool_ledger.entries)

        # Published agent versions may still contain a legacy output-format
        # instruction (for example, return a bare download URL).  A graph task
        # has a stricter runtime-owned terminal protocol, so append it to the
        # system prompt where it takes precedence over that stale instruction.
        sub_request.prompt = self._with_terminal_contract_prompt(sub_request.prompt, task)

        # Fast-path fallback: do not spend LLM calls when planner chose CALL_AGENT,
        # but the sub-agent ended up with zero executable operations.
        if not sub_request.resolved_operations and task.freshness_policy.value == "allow_memory":
            # No operations is not an execution error for a reasoning task.
            # The normal model path below can still return a bounded answer.
            pass
        elif not sub_request.resolved_operations:
            msg = "sub_agent_no_operations"
            ctx.extra["agent_execution_result"] = TaskCompletionDeclaration(
                completion="unfulfillable",
                report=msg,
                limitation={"code": msg, "message": "The selected agent has no compatible operation.", "action": "none"},
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

                    # Collect verified attachments for terminal synthesis delivery.
                    operation_name = str(runtime_event.data.get("tool") or "")
                    if self._deletes_artifact(operation_name) and bool(runtime_event.data.get("success")):
                        deleted_refs = [
                            item for item in runtime_event.data.get("artifact_refs") or []
                            if isinstance(item, dict)
                        ]
                        if deleted_refs:
                            for item in deleted_refs:
                                state.mark_artifact_deleted(str(item.get("artifact_id") or ""))
                        elif isinstance(result_payload, dict):
                            state.mark_artifact_deleted(str(result_payload.get("artifact_id") or ""))
                    if self._creates_downloadable_artifact(operation_name) and bool(runtime_event.data.get("success")):
                        artifacts.extend(
                            item for item in runtime_event.data.get("artifact_refs") or []
                            if isinstance(item, dict)
                        )

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
                execution = await self._commit_declaration(
                    task=task,
                    model=model,
                    observed=self._commit_observation(ledger_entries=state.tool_ledger.entries[ledger_start:], artifacts=artifacts),
                )
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
                    sources=sub_sources,
                    verified_artifacts=artifacts,
                )
                await self._externalize_large_results(verified, lifecycle_agent_execution_id or task.task_id)
                ctx.extra["agent_execution_result"] = execution
                ctx.extra["agent_execution_verified"] = verified

        # Keep sources available to memory/writeback. Synthesis receives the
        # verified per-task projection persisted with its final plan instead.
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
    ) -> TaskExecutionReceipt:
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
        verified = ctx.extra.pop("agent_execution_verified", {})
        if not isinstance(execution, TaskCompletionDeclaration):
            raise TaskExecutionError(
                code="agent_task_completion_missing",
                message="Agent did not return a terminal task completion",
                retryable=True,
            )
        return TaskExecutionReceipt(declaration=execution, verified=verified if isinstance(verified, dict) else {})

    def _commit_observation(self, *, ledger_entries: List[Any], artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bounded, runtime-authored evidence projection for the tool-free commit pass."""
        results = []
        for entry in ledger_entries:
            if getattr(entry, "status", None) != "succeeded" or not getattr(entry, "success", False):
                continue
            results.append({
                "result_ref": str(getattr(entry, "result_ref", None) or getattr(entry, "call_id", "")),
                "operation": str(getattr(entry, "operation", "")),
                "result_preview": str(getattr(entry, "result_preview", "") or "")[:1200],
            })
        manifests = [{
            "artifact_ref": str(item.get("artifact_id") or ""),
            "file_name": str(item.get("file_name") or item.get("name") or "artifact"),
            "content_type": str(item.get("content_type") or ""),
            "size_bytes": item.get("size_bytes"),
        } for item in self._dedupe_artifacts(artifacts)]
        return {"results": results[:20], "artifacts": manifests[:20]}

    @staticmethod
    async def _externalize_large_results(verified: Dict[str, Any], scope: str) -> None:
        """Keep large tool payloads in backend object storage, never in task JSONB."""
        settings = get_settings()
        bucket = settings.S3_BUCKET_CHAT_UPLOADS
        for record in verified.get("result_records") or []:
            if not isinstance(record, dict) or record.get("payload") is None:
                continue
            try:
                body = json.dumps(record["payload"], ensure_ascii=False, default=str).encode("utf-8")
            except (TypeError, ValueError):
                continue
            if len(body) <= 4096:
                continue
            result_ref = str(record.get("result_ref") or "result")
            key = f"runtime/results/{scope}/{result_ref}.json"
            uploaded = await s3_manager.upload_content_sync(
                bucket=bucket,
                key=key,
                content=body,
                content_type="application/json",
                metadata={"runtime_result": "true", "result_ref": result_ref},
            )
            if uploaded:
                record["payload_ref"] = {"bucket": bucket, "key": key, "size_bytes": len(body), "content_type": "application/json"}
                record["payload"] = None

    async def _commit_declaration(
        self,
        *,
        task: TaskRequest,
        model: Optional[str],
        observed: Dict[str, Any],
    ) -> TaskCompletionDeclaration:
        """Run the terminal commit independently from the tool-decision loop.

        This call has no tool payload and therefore cannot execute operations.
        Retrying it never replays an already completed operation attempt.
        """
        commit_prompt = self._with_terminal_contract_prompt(
            "You are in the commit phase. Tools are disabled. Use only the runtime observation below; "
            "do not invent unseen data or artifact references.",
            task,
        )
        messages = [
            {"role": "system", "content": commit_prompt},
            {"role": "user", "content": json.dumps({
                "task": {"instructions": task.instructions, "inputs": task.inputs},
                "runtime_observation": observed,
            }, ensure_ascii=False, default=str)},
        ]
        last_error: Optional[Exception] = None
        for _attempt in range(2):
            try:
                content = await self._tool_runtime.llm.call(
                    messages=messages,
                    model=model,
                    temperature=0.0,
                    max_tokens=1800,
                    timeout_s=30,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "task_completion_declaration",
                            "schema": task_completion_json_schema(task),
                            "strict": False,
                        },
                    },
                )
                return parse_task_completion_declaration(content)
            except Exception as exc:
                last_error = exc
                messages.append({"role": "user", "content": "Return the declaration again as one valid JSON object matching the schema. Do not add prose."})
        raise ValueError(f"commit declaration invalid: {last_error}")

    @staticmethod
    def _verified_task_result(
        *, task: TaskRequest, ledger_entries: List[Any], sources: List[Dict[str, Any]],
        verified_artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
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
                "result_ref": str(getattr(entry, "result_ref", None) or getattr(entry, "call_id", "")),
                "call_id": str(getattr(entry, "call_id", "")),
                "operation": operation,
                "canonical_operation": normalized,
                "result_fingerprint": getattr(entry, "result_fingerprint", None),
                "result_preview": getattr(entry, "result_preview", None),
                "retrieval": is_retrieval,
            }
            receipts.append(receipt)
            evidence[receipt["call_id"]] = {"operation": operation, "result_fingerprint": receipt["result_fingerprint"]}
            if normalized in {"project_memory.mark", "memory.mark"}:
                memory_candidates.append({
                    "call_id": receipt["call_id"],
                    "result_fingerprint": receipt["result_fingerprint"],
                    "status": "accepted_candidate",
                })
        artifacts = AgentExecutor._dedupe_artifacts(list(verified_artifacts or []))
        for artifact in artifacts:
            artifact["artifact_ref"] = str(artifact.get("artifact_id") or "")
        return {
            "status": "observed",
            "fresh_retrieval": fresh_retrieval,
            "receipts": receipts,
            "evidence": evidence,
            "artifacts": artifacts,
            "sources": [dict(item) for item in sources if isinstance(item, dict)],
            "memory_candidates": memory_candidates,
            "result_records": [
                {
                    "result_ref": str(getattr(entry, "result_ref", None) or getattr(entry, "call_id", "")),
                    "call_id": str(getattr(entry, "call_id", "")),
                    "operation": str(getattr(entry, "operation", "")),
                    "status": str(getattr(entry, "status", "")),
                    "success": bool(getattr(entry, "success", False)),
                    "payload": getattr(entry, "result_data", None),
                    "result_fingerprint": getattr(entry, "result_fingerprint", None),
                }
                for entry in ledger_entries
            ],
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
    def _deletes_artifact(operation_name: str) -> bool:
        normalized = str(operation_name or "").strip()
        return normalized in {"file.delete", "file_delete"} or normalized.endswith(".file.delete")

    @staticmethod
    def _is_url_only_response(content: str) -> bool:
        """Detect an artifact-only agent response without trusting its URL."""
        return bool(re.fullmatch(r"https?://[^\r\n]+", str(content or "").strip().strip("`")))

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
        """Compose sub-agent messages with the immutable task input contract.

        The complete typed ``task.inputs`` object is rendered as the final
        task-input block; there is no special legacy recall-input path.
        """
        query = task.instructions
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
            parts.append("[Task inputs]\n" + json.dumps(task.inputs, ensure_ascii=False, default=str)[:8000])
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
                    "receipts": list((output.get("verified") or {}).get("receipts") or [])[:8],
                    "evidence": (output.get("verified") or {}).get("evidence") or {},
                    "artifacts": list((output.get("verified") or {}).get("artifacts") or [])[:8],
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
            for artifact in (dependency.get("verified") or {}).get("artifacts") or []:
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
                attachment_lines.append(
                    f"- {file_name} (artifact_id={artifact_id}; snippet_status={snippet_status})"
                )
            if len(attachment_lines) > 1:
                final_query = "\n\n".join(["\n".join(attachment_lines), final_query])

        output_contract = [
            "[Terminal task completion declaration]",
            "Return exactly one JSON object and no prose or markdown.",
            "The runtime owns tool execution, evidence and artifact storage. Do not copy raw tool results into outputs.",
            "Use direct output values: outputs.<key> is the value itself, never {data,text,artifacts}.",
            "Select only relevant runtime results with evidence_selections=[{result_ref,output_keys,description}] and relevant files with artifact_selections=[{artifact_ref,output_key,description}].",
            "completion is fulfilled, needs, or unfulfillable. fulfilled requires every required output; needs requires non-empty needs; unfulfillable requires limitation.",
            "Required fields are completion, report, outputs, evidence_selections, artifact_selections, and needs. limitation is required only for unfulfillable.",
            "A need has ref, key, kind (data|artifact|decision), description, schema, required, and context.",
        ]
        if task.expected_outputs:
            output_contract.append(
                "Expected outputs (follow required and schema exactly):\n" +
                json.dumps([item.model_dump(mode="json", by_alias=True) for item in task.expected_outputs], ensure_ascii=False)
            )
        final_query = "\n\n".join(["\n".join(output_contract), final_query])

        non_system.append({"role": "user", "content": final_query})
        return non_system

    @staticmethod
    def _with_terminal_contract_prompt(prompt: str, task: TaskRequest) -> str:
        expected = json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in task.expected_outputs],
            ensure_ascii=False,
        )
        return "\n\n".join(part for part in [
            str(prompt or "").strip(),
            "# RUNTIME TASK COMPLETION DECLARATION\n"
            "This contract overrides any conflicting output format. Return one strict JSON object only. "
            "The runtime, not the agent, executes tools and owns their evidence and artifacts. "
            "outputs is a JSON object of direct values keyed by expected output key: never use data/text/artifacts wrappers. "
            "Select relevant runtime evidence only via evidence_selections ({result_ref,output_keys,description}) and artifacts only via artifact_selections ({artifact_ref,output_key,description}). "
            "Use completion=fulfilled only when required outputs are present; completion=needs only with non-empty needs; completion=unfulfillable only with limitation. "
            f"Expected outputs (including required/schema): {expected}. "
            "Your declaration must conform to this JSON Schema: "
            f"{json.dumps(task_completion_json_schema(task), ensure_ascii=False)}.",
        ] if part)

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
    def _parse_needs_from_content(raw: str) -> List[DiscoveredNeed]:
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
    def _extract_needs_from_dict(parsed: Dict[str, Any]) -> List[DiscoveredNeed]:
        needs_data = parsed.get("needs")
        if not isinstance(needs_data, list):
            return []
        result: List[DiscoveredNeed] = []
        for item in needs_data:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            result.append(
                DiscoveredNeed(
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
