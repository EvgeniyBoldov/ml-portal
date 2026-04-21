"""
Synthesizer — streams the final answer to the user from WorkingMemory.

When Planner emits a FINAL step, Pipeline calls Synthesizer to produce the
user-visible answer. Inputs:
    * goal (from WorkingMemory)
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
from app.runtime.events import RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory
from app.services.system_llm_role_service import SystemLLMRoleService

logger = get_logger(__name__)


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

    async def stream(
        self,
        *,
        memory: WorkingMemory,
        run_id: UUID,
        model: Optional[str] = None,
        planner_hint: Optional[str] = None,
        chunk_size: int = 20,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        sources = list(memory.memory_state.get("sources") or [])
        sources = sources[:20]

        # Short-circuit: single successful agent_result with non-trivial text.
        short_answer = self._short_circuit_answer(memory)
        if short_answer and not planner_hint:
            logger.info("Synthesizer short-circuit for run=%s", run_id)
            yield RuntimeEvent.status("synthesizing", short_circuit=True)
            for i in range(0, len(short_answer), chunk_size):
                yield RuntimeEvent.delta(short_answer[i : i + chunk_size])
            memory.final_answer = short_answer
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
        messages = self._build_messages(
            memory,
            planner_hint=planner_hint,
            system_prompt=system_prompt,
        )
        buffer: List[str] = []
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
                memory.final_error = str(exc)
                return

        full = "".join(buffer).strip()
        if not full:
            # Fallback: stitched summaries.
            full = self._stitched_fallback(memory)
            for i in range(0, len(full), chunk_size):
                yield RuntimeEvent.delta(full[i : i + chunk_size])

        memory.final_answer = full
        yield RuntimeEvent.final(full, sources=sources, run_id=str(run_id))

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _short_circuit_answer(memory: WorkingMemory) -> Optional[str]:
        successful = [r for r in memory.agent_results if r.success]
        if len(successful) != 1:
            return None
        text = (successful[0].summary or "").strip()
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
    def _build_messages(
        memory: WorkingMemory,
        *,
        planner_hint: Optional[str],
        system_prompt: str,
    ) -> List[Dict[str, str]]:
        parts: List[str] = []
        parts.append(f"Цель: {memory.goal or '(не указана)'}")
        if memory.dialogue_summary:
            parts.append(f"Контекст диалога:\n{memory.dialogue_summary[:1500]}")

        if memory.agent_results:
            parts.append("Результаты агентов:")
            for r in memory.agent_results[-8:]:
                status = "OK" if r.success else "FAIL"
                parts.append(f"- [{r.agent_slug}] ({status}) {r.summary[:400]}")

        if memory.facts:
            parts.append("Факты:")
            for f in memory.facts[-20:]:
                parts.append(f"- {f.text[:200]}")

        if planner_hint:
            parts.append(f"Подсказка планировщика: {planner_hint[:400]}")

        user = "\n\n".join(parts)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _stitched_fallback(memory: WorkingMemory) -> str:
        parts: List[str] = []
        for r in memory.agent_results:
            if r.success and r.summary:
                parts.append(r.summary)
        if not parts and memory.facts:
            parts = [f.text for f in memory.facts[-10:]]
        return "\n\n".join(parts) or "Не удалось собрать ответ."
