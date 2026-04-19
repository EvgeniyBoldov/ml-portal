"""MemoryWriter — write path at turn end.

Takes the finished `WorkingMemory` plus the raw turn text (what the
user said, what we finally answered) and produces two side effects:

    1. Upserted Facts in `FactStore` via `FactExtractor` + supersede.
    2. Updated `DialogueSummary` in `SummaryStore` via `SummaryCompactor`,
       with `raw_tail` maintained locally (string concat + clip).

If the chat has no chat_id (e.g. sandbox turn), the writer simply
no-ops — there is nothing to persist against.

Failure policy
--------------
A memory-write failure must NEVER surface as a turn failure. Any
exception inside `finalize` is logged and swallowed. The worst that
can happen is we miss one turn of memory updates; the user still
gets their answer.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_extractor import (
    FactExtractor,
    KnownFactSnippet,
)
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.summary_compactor import SummaryCompactor
from app.runtime.memory.summary_store import SummaryStore
from app.runtime.memory.transport import TurnMemory

logger = get_logger(__name__)


RAW_TAIL_MAX_CHARS = 2000


class MemoryWriter:
    """Persist a turn's memory effects."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._summary_store = SummaryStore(session)
        self._extractor = FactExtractor(session=session, llm_client=llm_client)
        self._compactor = SummaryCompactor(session=session, llm_client=llm_client)

    async def finalize(
        self,
        *,
        memory: TurnMemory,
        user_message: str,
        assistant_final: Optional[str],
    ) -> None:
        """Write facts + summary. Safe to call with empty agent_results
        (e.g. planner returned DIRECT_ANSWER with no tool use).
        """
        if memory.chat_id is None:
            # Sandbox or other ephemeral context — nothing to persist.
            return

        try:
            await self._write_facts(memory, user_message)
            await self._write_summary(memory, user_message, assistant_final or "")
        except Exception as exc:  # noqa: BLE001
            # We deliberately swallow: a memory-write failure must never
            # bubble up and break the turn the user just paid for.
            logger.warning(
                "MemoryWriter.finalize failed for chat=%s: %s",
                memory.chat_id, exc,
            )

    # ---------------------------------------------------------------- facts

    async def _write_facts(
        self,
        memory: TurnMemory,
        user_message: str,
    ) -> None:
        known = [
            KnownFactSnippet(subject=s, value=v)
            for s, v in memory.iter_known_subjects()
        ]
        new_facts = await self._extractor.extract(
            user_message=user_message,
            agent_results=memory.agent_results,
            known_facts=known,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            chat_id=memory.chat_id,
        )
        for fact in new_facts:
            await self._fact_store.upsert_with_supersede(fact)

    # -------------------------------------------------------------- summary

    async def _write_summary(
        self,
        memory: TurnMemory,
        user_message: str,
        assistant_final: str,
    ) -> None:
        assert memory.chat_id is not None  # guarded by caller

        new_summary = await self._compactor.compact(
            previous=memory.summary,
            user_message=user_message,
            assistant_final=assistant_final,
            agent_results=memory.agent_results,
            turn_number=memory.turn_number,
            chat_id=memory.chat_id,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
        )
        # Maintain raw_tail locally — the LLM is explicitly told not to
        # touch it. We append user+assistant pair to the existing tail
        # and clip from the front to respect the char budget.
        new_summary.raw_tail = _rebuild_raw_tail(
            memory.summary.raw_tail, user_message, assistant_final,
        )
        new_summary.chat_id = memory.chat_id

        await self._summary_store.save(new_summary)


def _rebuild_raw_tail(
    previous_tail: str,
    user_message: str,
    assistant_final: str,
) -> str:
    """Append the current turn to the tail and clip from the front.

    Format is deliberately minimal — this buffer is a cheap fallback
    for small-context local models, not a formatted transcript.
    """
    pieces = []
    if previous_tail:
        pieces.append(previous_tail.rstrip())
    if user_message:
        pieces.append(f"user: {user_message.strip()}")
    if assistant_final:
        pieces.append(f"assistant: {assistant_final.strip()}")
    joined = "\n".join(pieces)
    if len(joined) <= RAW_TAIL_MAX_CHARS:
        return joined
    # Clip from the front — keep the most recent content.
    return joined[-RAW_TAIL_MAX_CHARS:]
