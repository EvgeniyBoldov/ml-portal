"""
Synthesizer — streams the final answer to the user from RuntimeTurnState.

When Planner emits a FINAL step, Pipeline calls Synthesizer to produce the
user-visible answer. Inputs:
    * canonical answer_brief prepared by planning/finalization
    * optional files and citations to reference

Output: a stream of DELTA events followed by a FINAL event carrying full text
and accumulated sources. This is the only place in runtime that directly
streams text to the user for orchestrated runs.

When finalization already prepared a canonical user-ready answer_brief, the
synthesizer may short-circuit and restream it directly.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot, serialize_limits
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.input_builders import SynthesizerInputBuilder
from app.runtime.llm.streaming import RoleStreamingCall, StreamDelta, StreamError, StreamTurn
from app.runtime.turn_state import RuntimeTurnState
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.model_call_config_service import ModelCallConfigService

logger = get_logger(__name__)

# Default chunk size for fallback synthesis streaming.
# Can be overridden via platform_config.runtime.synth_chunk_size if needed.
DEFAULT_SYNTH_CHUNK_SIZE = 20

# Last-resort prompt used only if the DB role cannot be loaded (schema drift,
# migration not run, etc.). Admins should edit the SYNTHESIZER row in
# `system_llm_roles` rather than this constant.
_FALLBACK_SYSTEM_PROMPT = (
    "Ты — редактор финального ответа корпоративного AI-портала. "
    "Преобразуй answer_brief в точный и лаконичный ответ для пользователя, "
    "не меняя смысл и не добавляя новые факты."
)
_FILE_DELIVERY_RULE = (
    "Сгенерированные файлы доставляются интерфейсом отдельными вложениями. "
    "Не добавляй в текст markdown-ссылки, URL или списки файлов; при необходимости "
    "можно кратко упомянуть имя готового файла."
)

_ROLE_PROMPT_SECTIONS = [
    ("identity", "IDENTITY"),
    ("mission", "MISSION"),
    ("rules", "RULES"),
    ("safety", "SAFETY"),
    ("output_requirements", "OUTPUT REQUIREMENTS"),
]


def _compile_role_prompt(role_config: Dict[str, object], role_override: Optional[Dict[str, object]]) -> str:
    """Recompile system prompt from role config parts + optional sandbox overrides."""
    parts: list[str] = []
    for field, heading in _ROLE_PROMPT_SECTIONS:
        base = role_config.get(field)
        override_val = role_override.get(field) if isinstance(role_override, dict) else None
        val = override_val if override_val is not None else base
        if val:
            parts.append(f"# {heading}\n{val}")

    examples = role_config.get("examples")
    override_examples = role_override.get("examples") if isinstance(role_override, dict) else None
    effective_examples = override_examples if override_examples is not None else examples
    if effective_examples:
        parts.append("# EXAMPLES")
        for i, example in enumerate(effective_examples, 1):
            parts.append(f"## Example {i}")
            if isinstance(example, dict):
                if example.get("description"):
                    parts.append(f"Description: {example['description']}")
                if example.get("input"):
                    parts.append(f"Input: {example['input']}")
                if example.get("output"):
                    parts.append(f"Output: {example['output']}")
            parts.append("")

    return "\n\n".join(parts) if parts else (role_config.get("prompt") or _FALLBACK_SYSTEM_PROMPT)


class Synthesizer:
    """Streams the final answer from accumulated memory."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self._input_builder = SynthesizerInputBuilder()
        self._streaming_call = RoleStreamingCall(session=session, llm_client=llm_client)

    async def stream(
        self,
        *,
        runtime_state: RuntimeTurnState,
        run_id: UUID,
        model: Optional[str] = None,
        answer_brief: Optional[str] = None,
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize",
        platform_config: Optional[Dict[str, object]] = None,
        sandbox_overrides: Optional[Dict[str, object]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        chunk_size: int = DEFAULT_SYNTH_CHUNK_SIZE,
        logging_level: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        chunk_size = self._resolve_chunk_size(
            base_chunk_size=chunk_size,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        synthesis_run_id = str(uuid4())
        synthesis_status = "completed"

        # Load synthesizer role config early for context snapshot
        synth_role_cfg = await self._load_role_config()
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get("synthesizer")
        if isinstance(role_override, dict):
            if role_override.get("model"):
                synth_role_cfg["model"] = str(role_override["model"])
            if role_override.get("temperature") is not None:
                synth_role_cfg["temperature"] = float(role_override["temperature"])
        synth_prompt = _compile_role_prompt(synth_role_cfg, role_override if isinstance(role_override, dict) else None)
        synth_prompt = f"{synth_prompt}\n\n# FILE DELIVERY\n{_FILE_DELIVERY_RULE}"

        if budget_registry is not None:
            synthesis_limits = None
            if budget_resolver is not None:
                try:
                    synthesis_limits = await budget_resolver.resolve_orchestrator("synthesizer", sandbox_overrides)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to resolve synthesizer limits: %s", exc)
            budget_registry.register(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_id=str(run_id),
                role="synthesizer",
                limits=synthesis_limits,
            )
            init_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="init") or {}
            yield RuntimeEvent.budget_snapshot(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_type="run",
                parent_entity_id=str(run_id),
                role="synthesizer",
                own=init_payload.get("own", {}),
                limits=init_payload.get("limits"),
                delta={},
                reason="init",
                at_ms=init_payload.get("at_ms"),
            )
        else:
            synthesis_limits = None
        yield RuntimeEvent.synthesis_start(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
            context_snapshot=compact_snapshot(
                inputs={
                    "answer_brief": answer_brief,
                    "goal": runtime_state.goal,
                },
                prompt=prompt_snapshot(synth_prompt, logging_level),
                limits=serialize_limits(synthesis_limits),
                meta={
                    "role": "synthesizer",
                    "model": synth_role_cfg.get("model") or model,
                },
            ),
        )
        # Sources from memory_bundle if available
        sources: List[dict] = self._extract_sources(runtime_state)

        # Attachments generated by agents (file.generate results)
        attachments = self._extract_attachments(runtime_state)

        # Short-circuit based on explicit strategy (structural, not heuristic)
        resolved_answer_brief = str(answer_brief or runtime_state.answer_brief or "").strip()

        if final_answer_strategy == "verbatim" and resolved_answer_brief:
            short_answer = resolved_answer_brief
            logger.info("Synthesizer verbatim short-circuit for run=%s", run_id)
            yield RuntimeEvent.status("synthesizing", short_circuit=True, mode="verbatim")
            for i in range(0, len(short_answer), chunk_size):
                yield RuntimeEvent.delta(short_answer[i : i + chunk_size])
            runtime_state.final_answer = short_answer
            yield RuntimeEvent.status(
                "final_answer_marker",
                producer="synthesizer_verbatim",
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
                content=short_answer,
            )
            yield RuntimeEvent.final(short_answer, sources=sources, run_id=str(run_id), attachments=attachments)
            if budget_registry is not None:
                final_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="finalize") or {}
                yield RuntimeEvent.budget_snapshot(
                    entity_type="synthesis_run",
                    entity_id=synthesis_run_id,
                    parent_entity_type="run",
                    parent_entity_id=str(run_id),
                    role="synthesizer",
                    own=final_payload.get("own", {}),
                    limits=final_payload.get("limits"),
                    delta={},
                    reason="finalize",
                    at_ms=final_payload.get("at_ms"),
                )
            yield RuntimeEvent.synthesis_end(
                synthesis_id=synthesis_run_id,
                run_id=str(run_id),
                status=synthesis_status,
            )
            return

        if final_answer_strategy == "use_agent_result" and resolved_answer_brief:
            short_answer = resolved_answer_brief
            logger.info("Synthesizer use_agent_result short-circuit for run=%s", run_id)
            yield RuntimeEvent.status("synthesizing", short_circuit=True, mode="use_agent_result")
            for i in range(0, len(short_answer), chunk_size):
                yield RuntimeEvent.delta(short_answer[i : i + chunk_size])
            runtime_state.final_answer = short_answer
            yield RuntimeEvent.status(
                "final_answer_marker",
                producer="synthesizer_agent_result",
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
                content=short_answer,
            )
            yield RuntimeEvent.final(short_answer, sources=sources, run_id=str(run_id), attachments=attachments)
            if budget_registry is not None:
                final_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="finalize") or {}
                yield RuntimeEvent.budget_snapshot(
                    entity_type="synthesis_run",
                    entity_id=synthesis_run_id,
                    parent_entity_type="run",
                    parent_entity_id=str(run_id),
                    role="synthesizer",
                    own=final_payload.get("own", {}),
                    limits=final_payload.get("limits"),
                    delta={},
                    reason="finalize",
                    at_ms=final_payload.get("at_ms"),
                )
            yield RuntimeEvent.synthesis_end(
                synthesis_id=synthesis_run_id,
                run_id=str(run_id),
                status=synthesis_status,
            )
            return

        # Full synthesis path. Role configuration owns prompt, model and
        # temperature. Call limits and transport parameters belong to the
        # selected model deployment.
        # caller-supplied `model` still wins when provided.
        role_cfg = synth_role_cfg
        system_prompt = synth_prompt
        effective_model = model or role_cfg.get("model")
        params: Dict[str, float] = {}
        if role_cfg.get("temperature") is not None:
            params["temperature"] = role_cfg["temperature"]

        yield RuntimeEvent.status("synthesizing")
        messages = self._input_builder.build(
            runtime_state=runtime_state,
            answer_brief=resolved_answer_brief,
            system_prompt=system_prompt,
        )
        full = ""
        try:
            model_call_config = await ModelCallConfigService(self.session).resolve(effective_model)
            max_retries = model_call_config.max_retries
        except Exception as exc:  # noqa: BLE001
            # A role prompt can be served from a fallback even while the model
            # registry is temporarily unavailable. Keep the same safe default
            # used by ModelCallConfigService in that degraded mode.
            logger.warning("Failed to resolve synthesizer model retry policy: %s", exc)
            max_retries = 2
        for attempt in range(max_retries + 1):
            llm_call_id = str(uuid4())
            retry_scheduled = False
            # Emit before opening the stream so a provider timeout/error still has
            # a stable LLM child in the sandbox journal.
            yield RuntimeEvent.llm_request(
                llm_call_id=llm_call_id,
                model=effective_model or "unknown",
                messages=messages,
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
                purpose="final_answer",
                actor_type="synthesizer",
                actor_entity_id=synthesis_run_id,
            )
            async for stream_event in self._streaming_call.invoke_stream(
                role=SystemLLMRoleType.SYNTHESIZER,
                messages=messages,
                llm_call_id=llm_call_id,
                role_config=role_cfg,
                model_override=effective_model,
                params_override=params or None,
                sandbox_overrides=sandbox_overrides,
                budget_registry=budget_registry,
                budget_entity_id=synthesis_run_id,
            ):
                if isinstance(stream_event, StreamDelta):
                    if stream_event.chunk:
                        yield RuntimeEvent.delta(stream_event.chunk)
                    continue
                if isinstance(stream_event, StreamError):
                    yield RuntimeEvent.llm_response(
                        llm_call_id=llm_call_id,
                        model=effective_model or "unknown",
                        error_type=stream_event.error_type,
                        error_code=stream_event.code,
                        retryable=stream_event.recoverable,
                        retry_after_ms=stream_event.retry_after_ms,
                        parent_entity_type="synthesis_run",
                        parent_entity_id=synthesis_run_id,
                        purpose="final_answer",
                        actor_type="synthesizer",
                        actor_entity_id=synthesis_run_id,
                    )
                    if stream_event.recoverable and attempt < max_retries:
                        retry_delay_ms = self._retry_delay_ms(
                            attempt=attempt,
                            retry_after_ms=stream_event.retry_after_ms,
                        )
                        yield RuntimeEvent(
                            RuntimeEventType.PROTOCOL_RETRY,
                            {
                                "reason": "transport_error",
                                "attempt": attempt + 1,
                                "max_attempts": max_retries + 1,
                                "retry_delay_ms": retry_delay_ms,
                                "retry_after_ms": stream_event.retry_after_ms,
                                "parent_entity_type": "synthesis_run",
                                "parent_entity_id": synthesis_run_id,
                            },
                        )
                        await asyncio.sleep(retry_delay_ms / 1000)
                        retry_scheduled = True
                        break
                    synthesis_status = "failed"
                    yield RuntimeEvent.error(
                        stream_event.message,
                        recoverable=stream_event.recoverable,
                        error_code=stream_event.code,
                        user_message=stream_event.message,
                        operator_message=stream_event.message,
                        source="llm",
                        error_type=stream_event.error_type,
                        debug=stream_event.debug,
                        parent_entity_type="synthesis_run",
                        parent_entity_id=synthesis_run_id,
                    )
                    runtime_state.final_error = stream_event.message
                    yield RuntimeEvent.synthesis_end(
                        synthesis_id=synthesis_run_id,
                        run_id=str(run_id),
                        status=synthesis_status,
                    )
                    return
                if isinstance(stream_event, StreamTurn):
                    full = (stream_event.content or "").strip()
                    if budget_registry is not None:
                        delta_payload: Dict[str, int] = {}
                        if stream_event.tokens_in > 0:
                            delta_payload["tokens_in"] = stream_event.tokens_in
                        if stream_event.tokens_out > 0:
                            delta_payload["tokens_out"] = stream_event.tokens_out
                        if stream_event.tokens_total > 0:
                            delta_payload["tokens_total"] = stream_event.tokens_total
                        if stream_event.duration_ms > 0:
                            delta_payload["wall_time_ms"] = stream_event.duration_ms
                        if delta_payload:
                            snap = budget_registry.emit_snapshot(
                                synthesis_run_id,
                                reason="llm_turn",
                                delta=delta_payload,
                            ) or {}
                            yield RuntimeEvent.budget_snapshot(
                                entity_type="synthesis_run",
                                entity_id=synthesis_run_id,
                                parent_entity_type="run",
                                parent_entity_id=str(run_id),
                                role="synthesizer",
                                own=snap.get("own", {}),
                                limits=snap.get("limits"),
                                delta=delta_payload,
                                reason="llm_turn",
                                at_ms=snap.get("at_ms"),
                            )
                    yield RuntimeEvent.llm_response(
                        llm_call_id=stream_event.llm_call_id,
                        model=effective_model or stream_event.model or "unknown",
                        content=full, response_length=stream_event.response_length,
                        tokens_in=stream_event.tokens_in, tokens_out=stream_event.tokens_out,
                        tokens_total=stream_event.tokens_total, duration_ms=stream_event.duration_ms,
                        parent_entity_type="synthesis_run", parent_entity_id=synthesis_run_id,
                        purpose="final_answer", actor_type="synthesizer", actor_entity_id=synthesis_run_id,
                    )
            if retry_scheduled:
                continue
            break
        if not full:
            # Fallback: stitched summaries (LLM вернул пустой ответ).
            logger.warning(
                "Synthesizer LLM вернул пустой ответ для run=%s — используется fallback из agent_results",
                run_id,
            )
            full = self._stitched_fallback(runtime_state=runtime_state)
            for i in range(0, len(full), chunk_size):
                yield RuntimeEvent.delta(full[i : i + chunk_size])

        runtime_state.final_answer = full
        yield RuntimeEvent.status(
            "final_answer_marker",
            producer="synthesizer_llm",
            parent_entity_type="synthesis_run",
            parent_entity_id=synthesis_run_id,
            content=full,
        )
        yield RuntimeEvent.final(full, sources=sources, run_id=str(run_id), attachments=attachments)
        if budget_registry is not None:
            final_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="finalize") or {}
            yield RuntimeEvent.budget_snapshot(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_type="run",
                parent_entity_id=str(run_id),
                role="synthesizer",
                own=final_payload.get("own", {}),
                limits=final_payload.get("limits"),
                delta={},
                reason="finalize",
                at_ms=final_payload.get("at_ms"),
            )
        yield RuntimeEvent.synthesis_end(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
            status=synthesis_status,
        )

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _extract_attachments(
        runtime_state: RuntimeTurnState,
    ) -> List[Dict[str, Any]]:
        """Collect file.generate attachments from all agent results."""
        result: List[Dict[str, Any]] = []
        seen_artifact_ids: set[str] = set()
        for item in runtime_state.agent_results:
            item_attachments = item.get("attachments")
            if isinstance(item_attachments, list):
                for att in item_attachments:
                    artifact_id = str(att.get("artifact_id") or "").strip() if isinstance(att, dict) else ""
                    if not artifact_id or artifact_id in seen_artifact_ids:
                        continue
                    seen_artifact_ids.add(artifact_id)
                    result.append({
                        "artifact_id": artifact_id,
                        "file_name": att.get("file_name") or att.get("name") or "file",
                        "download_url": att.get("download_url") or f"/api/v1/files/{artifact_id}/download",
                        "content_type": att.get("content_type") or "",
                        "size_bytes": att.get("size_bytes"),
                    })
        return result

    @staticmethod
    def _extract_sources(
        runtime_state: RuntimeTurnState,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not runtime_state.memory_bundle or not runtime_state.memory_bundle.sections:
            return result
        for section in runtime_state.memory_bundle.sections:
            if section.name != "sources":
                continue
            for item in section.items[:20]:
                if isinstance(item.metadata, dict) and isinstance(item.metadata.get("source"), dict):
                    result.append(dict(item.metadata["source"]))
            break
        return result

    async def _load_role_config(self) -> Dict[str, object]:
        """Load SYNTHESIZER role config from DB with a safe fallback."""
        try:
            service = SystemLLMRoleService(self.session)
            return await service.get_role_config(SystemLLMRoleType.SYNTHESIZER)
        except Exception as exc:
            logger.warning(
                "Synthesizer role config load failed, falling back to defaults: %s",
                exc,
            )
            return {
                "prompt": _FALLBACK_SYSTEM_PROMPT,
                "model": None,
                "temperature": 0.3,
                "max_tokens": 2000,
            }

    @staticmethod
    def _stitched_fallback(
        *,
        runtime_state: RuntimeTurnState,
    ) -> str:
        parts: List[str] = []
        for item in runtime_state.agent_results:
            if bool(item.get("success", True)) and str(item.get("summary") or "").strip():
                parts.append(str(item.get("summary") or "").strip())
        if not parts and runtime_state.runtime_facts:
            parts = [item.text for item in runtime_state.runtime_facts[-10:]]
        result = "\n\n".join(parts)
        if not result:
            logger.warning("Synthesizer _stitched_fallback: нет ни agent_results ни runtime_facts — возвращается пустой ответ")
            return "Не удалось получить ответ. Попробуйте позже."
        return result

    @staticmethod
    def _retry_delay_ms(*, attempt: int, retry_after_ms: Optional[int]) -> int:
        """Bound retry delay and respect a provider supplied cooldown."""
        exponential_ms = min(10_000, 500 * (2 ** max(0, attempt)))
        if retry_after_ms is None:
            return exponential_ms
        return min(30_000, max(exponential_ms, max(0, retry_after_ms)))

    @staticmethod
    def _resolve_chunk_size(
        *,
        base_chunk_size: int,
        platform_config: Optional[Dict[str, object]],
        sandbox_overrides: Optional[Dict[str, object]],
    ) -> int:
        chunk_size = int(base_chunk_size) if int(base_chunk_size) > 0 else DEFAULT_SYNTH_CHUNK_SIZE
        runtime_cfg = (platform_config or {}).get("runtime")
        if isinstance(runtime_cfg, dict):
            value = runtime_cfg.get("synth_chunk_size")
            if isinstance(value, int) and value > 0:
                chunk_size = value
        sandbox_runtime = (sandbox_overrides or {}).get("runtime")
        if isinstance(sandbox_runtime, dict):
            value = sandbox_runtime.get("synth_chunk_size")
            if isinstance(value, int) and value > 0:
                chunk_size = value
        return max(1, chunk_size)
