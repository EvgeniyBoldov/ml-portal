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

import time
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.execution_limit import ExecutionLimitScope
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.input_builders import SynthesizerInputBuilder
from app.runtime.llm.limits import LLMLimitExceededError, apply_llm_limits, estimate_tokens
from app.runtime.turn_state import RuntimeTurnState
from app.services.execution_limits_service import ExecutionLimitsPayload, ExecutionLimitsService, apply_limits_override
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
        self._limits_service = ExecutionLimitsService(session)

    async def stream(
        self,
        *,
        runtime_state: RuntimeTurnState,
        run_id: UUID,
        model: Optional[str] = None,
        planner_hint: Optional[str] = None,
        platform_config: Optional[Dict[str, object]] = None,
        sandbox_overrides: Optional[Dict[str, object]] = None,
        chunk_size: int = DEFAULT_SYNTH_CHUNK_SIZE,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        chunk_size = self._resolve_chunk_size(
            base_chunk_size=chunk_size,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        # Sources from memory_bundle if available
        sources: List[str] = []
        if runtime_state.memory_bundle and runtime_state.memory_bundle.sections:
            for section in runtime_state.memory_bundle.sections:
                if section.name == "sources":
                    sources = [item.text for item in section.items[:20] if item.text]
                    break

        # Short-circuit: single successful agent_result with non-trivial text.
        short_answer = self._short_circuit_answer(runtime_state=runtime_state)
        is_informative_hint = planner_hint and "to be synthesized" not in planner_hint.lower()
        if short_answer and not is_informative_hint:
            logger.info("Synthesizer short-circuit for run=%s", run_id)
            yield RuntimeEvent.status("synthesizing", short_circuit=True)
            for i in range(0, len(short_answer), chunk_size):
                yield RuntimeEvent.delta(short_answer[i : i + chunk_size])
            runtime_state.final_answer = short_answer
            yield RuntimeEvent.final(short_answer, sources=sources, run_id=str(run_id))
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
        synthesis_run_id = f"{run_id}:synthesis:1"
        try:
            limits = await self._limits_service.get_effective(
                scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
                scope_ref="synthesizer",
            )
        except Exception:
            limits = ExecutionLimitsPayload()
        synth_override = ((sandbox_overrides or {}).get("orchestrator_limits") or {}).get("synthesizer")
        limits = apply_limits_override(limits, synth_override if isinstance(synth_override, dict) else None)
        input_tokens = estimate_tokens(str(messages))
        requested_output_tokens = int(params["max_tokens"]) if params.get("max_tokens") is not None else None
        try:
            boundary = apply_llm_limits(
                limits=limits,
                input_tokens=input_tokens,
                requested_output_tokens=requested_output_tokens,
            )
        except LLMLimitExceededError as exc:
            yield RuntimeEvent.error(
                str(exc),
                recoverable=False,
                error_code=exc.code,
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
            )
            runtime_state.final_error = str(exc)
            return
        if boundary.output_tokens is not None:
            params["max_tokens"] = int(boundary.output_tokens)
        buffer: List[str] = []
        started_at = time.monotonic()
        try:
            async for chunk in self.llm_client.chat_stream(
                messages,
                model=effective_model,
                params=params or None,
            ):
                if not chunk:
                    continue
                buffer.append(chunk)
                yield RuntimeEvent.delta(chunk)
        except Exception as exc:
            logger.error("Synthesizer LLM stream failed: %s", exc, exc_info=True)
            if not buffer:
                yield RuntimeEvent.error(f"Failed to synthesize answer: {exc}", recoverable=True)
                runtime_state.final_error = str(exc)
                return

        full = "".join(buffer).strip()
        yield RuntimeEvent.llm_turn(
            llm_call_id=llm_call_id,
            model=effective_model or "unknown",
            messages=messages,
            content=full,
            response_length=len(full),
            tokens_in=max(1, len(str(messages)) // 4),
            tokens_out=max(1, len(full) // 4) if full else 0,
            tokens_total=(max(1, len(str(messages)) // 4) + (max(1, len(full) // 4) if full else 0)),
            duration_ms=int((time.monotonic() - started_at) * 1000),
            parent_entity_type="synthesis_run",
            parent_entity_id=synthesis_run_id,
            purpose="final_answer",
            actor_type="synthesizer",
            actor_entity_id=synthesis_run_id,
        )
        if not full:
            # Fallback: stitched summaries.
            full = self._stitched_fallback(runtime_state=runtime_state)
            for i in range(0, len(full), chunk_size):
                yield RuntimeEvent.delta(full[i : i + chunk_size])

        runtime_state.final_answer = full
        yield RuntimeEvent.final(full, sources=sources, run_id=str(run_id))

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
        return "\n\n".join(parts) or "Не удалось собрать ответ."

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
