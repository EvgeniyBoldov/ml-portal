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
from app.runtime.events import RuntimeEvent
from app.runtime.memory.working_memory import WorkingMemory

logger = get_logger(__name__)


DEFAULT_SYSTEM_PROMPT = (
    "Ты — старший инженер корпоративного AI-портала. Сформируй точный, "
    "лаконичный и структурированный ответ для пользователя на основе "
    "предоставленных фактов и промежуточных результатов агентов. "
    "Не придумывай того, чего нет в фактах. Если данных не хватает — честно "
    "отметь это в конце ответа. Отвечай на русском, если пользователь писал "
    "на русском; иначе — на языке пользователя."
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

        # Full synthesis path.
        yield RuntimeEvent.status("synthesizing")
        messages = self._build_messages(memory, planner_hint=planner_hint)
        buffer: List[str] = []
        try:
            async for chunk in self.llm_client.chat_stream(messages, model=model):
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

    @staticmethod
    def _build_messages(
        memory: WorkingMemory,
        *,
        planner_hint: Optional[str],
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
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
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
