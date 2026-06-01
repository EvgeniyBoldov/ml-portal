"""
Synthesizer — streams the final answer to the user from RuntimeTurnState.

When Planner emits a FINAL step, Pipeline calls Synthesizer to produce the
user-visible answer. Inputs:
    * goal (from RuntimeTurnState)
    * facts (trimmed, deduped)
    * agent_results (summaries)
    * optional planner-suggested final_answer (used as a hint only)

Output: a stream of DELTA events followed by a FINAL event carrying full text
and accumulated sources. This is the only place in runtime that directly
streams text to the user for orchestrated runs.

For single-agent runs where we have one agent_result and no ambiguity, the
synthesizer short-circuits: it just restreams the agent's summary as deltas,
avoiding a redundant LLM call. Quality is preserved because the sub-agent
already produced a user-ready answer.
"""
from __future__ import annotations

from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.events import RuntimeEvent
from app.runtime.input_builders import SynthesizerInputBuilder
from app.runtime.llm.streaming import RoleStreamingCall, StreamDelta, StreamError, StreamTurn
from app.runtime.turn_state import RuntimeTurnState
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)

# Default chunk size for fallback synthesis streaming.
# Can be overridden via platform_config.runtime.synth_chunk_size if needed.
DEFAULT_SYNTH_CHUNK_SIZE = 20

# Last-resort prompt used only if the DB role cannot be loaded (schema drift,
# migration not run, etc.). Admins should edit the SYNTHESIZER row in
# `system_llm_roles` rather than this constant.
_FALLBACK_SYSTEM_PROMPT = (
    "Ты — старший инженер корпоративного AI-портала. Сформируй точный, "
    "лаконичный ответ для пользователя на основе предоставленных фактов и "
    "результатов агентов. Не придумывай ничего сверх фактов."
)


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
        planner_hint: Optional[str] = None,
        final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize",
        platform_config: Optional[Dict[str, object]] = None,
        sandbox_overrides: Optional[Dict[str, object]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        chunk_size: int = DEFAULT_SYNTH_CHUNK_SIZE,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        chunk_size = self._resolve_chunk_size(
            base_chunk_size=chunk_size,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        synthesis_run_id = f"{run_id}:synthesis:1"
        synthesis_status = "completed"

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
        yield RuntimeEvent.synthesis_start(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
        )
        # Sources from memory_bundle if available
        sources: List[str] = []
        if runtime_state.memory_bundle and runtime_state.memory_bundle.sections:
            for section in runtime_state.memory_bundle.sections:
                if section.name == "sources":
                    sources = [item.text for item in section.items[:20] if item.text]
                    break

        # Short-circuit based on explicit strategy (structural, not heuristic)
        if final_answer_strategy == "verbatim" and planner_hint:
            # Stream the planner's final_answer directly without LLM synthesis
            short_answer = planner_hint
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
            yield RuntimeEvent.final(short_answer, sources=sources, run_id=str(run_id))
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

        if final_answer_strategy == "use_agent_result":
            # Use single successful agent result directly
            short_answer = self._short_circuit_answer(runtime_state=runtime_state)
            if short_answer:
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
                yield RuntimeEvent.final(short_answer, sources=sources, run_id=str(run_id))
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

        # Full synthesis path. Load role-level config (prompt + model +
        # temperature + max_tokens) from the SYNTHESIZER system LLM role;
        # caller-supplied `model` still wins when provided.
        role_cfg = await self._load_role_config()
        system_prompt = role_cfg["prompt"]
        effective_model = model or role_cfg.get("model")
        params: Dict[str, float] = {}
        if role_cfg.get("temperature") is not None:
            params["temperature"] = role_cfg["temperature"]
        if role_cfg.get("max_tokens") is not None:
            params["max_tokens"] = role_cfg["max_tokens"]

        yield RuntimeEvent.status("synthesizing")
        messages = self._input_builder.build(
            runtime_state=runtime_state,
            planner_hint=planner_hint,
            system_prompt=system_prompt,
        )
        llm_call_id = f"{run_id}:synthesis-llm:1"
        full = ""
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
                synthesis_status = "failed"
                yield RuntimeEvent.error(
                    stream_event.message,
                    recoverable=stream_event.recoverable,
                    error_code=stream_event.code,
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
                yield RuntimeEvent.llm_turn(
                    llm_call_id=stream_event.llm_call_id,
                    model=effective_model or stream_event.model or "unknown",
                    messages=stream_event.messages,
                    content=full,
                    response_length=stream_event.response_length,
                    tokens_in=stream_event.tokens_in,
                    tokens_out=stream_event.tokens_out,
                    tokens_total=stream_event.tokens_total,
                    duration_ms=stream_event.duration_ms,
                    parent_entity_type="synthesis_run",
                    parent_entity_id=synthesis_run_id,
                    purpose="final_answer",
                    actor_type="synthesizer",
                    actor_entity_id=synthesis_run_id,
                )
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
        yield RuntimeEvent.final(full, sources=sources, run_id=str(run_id))
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
    def _short_circuit_answer(
        *,
        runtime_state: RuntimeTurnState,
    ) -> Optional[str]:
        successful: List[str] = []
        for item in runtime_state.agent_results:
            if not bool(item.get("success", True)):
                continue
            text = str(item.get("summary") or "").strip()
            if text:
                successful.append(text)
        if len(successful) != 1:
            return None
        text = successful[0]
        if len(text) < 40:
            return None
        return text

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
