"""SummaryCompactor — updates the per-chat structured summary.

Called by `MemoryWriter.finalize` once per turn, after FactExtractor.
Reads the previous `SummaryDTO` and the current turn's delta, returns
a new `SummaryDTO` that the writer then hands to `SummaryStore.save`.

The `raw_tail` field is maintained by the writer (pure string
concatenation + truncation), not by the LLM — we explicitly instruct
the model NOT to touch it.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet

logger = get_logger(__name__)


MAX_GOALS = 5
MAX_DONE = 10
MAX_ENTITIES = 10
MAX_OPEN_QUESTIONS = 5
MAX_ITEM_LEN = 120


class _LLMSummaryOutput(BaseModel):
    goals: List[str] = Field(default_factory=list)
    done: List[str] = Field(default_factory=list)
    entities: Dict[str, str] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)


class SummaryCompactor:
    """Single-call structured summarizer."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._structured = StructuredLLMCall(
            session=session, llm_client=llm_client
        )

    async def compact(
        self,
        *,
        previous: SummaryDTO,
        user_message: str,
        assistant_final: str,
        agent_results: Sequence[AgentResultSnippet],
        turn_number: int,
        chat_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> SummaryDTO:
        """Return a NEW SummaryDTO. On any failure returns a conservative
        fallback that keeps previous structured fields and just bumps
        last_updated_turn — we never drop a turn on memory errors.
        """
        payload = {
            "previous": {
                "goals": previous.goals,
                "done": previous.done,
                "entities": previous.entities,
                "open_questions": previous.open_questions,
                # raw_tail intentionally omitted — the LLM must not touch it
                "last_updated_turn": previous.last_updated_turn,
            },
            "turn_delta": {
                "user_message": user_message,
                "assistant_final": assistant_final,
                "agent_results": [r.model_dump() for r in agent_results],
            },
            "turn_number": turn_number,
        }

        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.SUMMARY_COMPACTOR,
                payload=payload,
                schema=_LLMSummaryOutput,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                fallback_factory=lambda _raw: _LLMSummaryOutput(),
            )
            out = result.value
        except StructuredCallError as exc:
            logger.warning("SummaryCompactor structured call failed: %s", exc)
            return self._fallback(previous, turn_number)
        except Exception as exc:  # noqa: BLE001 — never break the turn
            logger.warning("SummaryCompactor unexpected error: %s", exc)
            return self._fallback(previous, turn_number)

        return SummaryDTO(
            chat_id=previous.chat_id,
            goals=_clip_list(out.goals, MAX_GOALS),
            done=_clip_list(out.done, MAX_DONE),
            entities=_clip_map(out.entities, MAX_ENTITIES),
            open_questions=_clip_list(out.open_questions, MAX_OPEN_QUESTIONS),
            raw_tail=previous.raw_tail,          # writer maintains this
            last_updated_turn=turn_number,
        )

    # ------------------------------------------------------------ helpers ---

    @staticmethod
    def _fallback(previous: SummaryDTO, turn_number: int) -> SummaryDTO:
        """Keep previous structured fields verbatim, bump turn only."""
        copy = deepcopy(previous)
        copy.last_updated_turn = turn_number
        return copy


def _clip_list(items: List[str], cap: int) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in items:
        v = (raw or "").strip()[:MAX_ITEM_LEN]
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= cap:
            break
    return out


def _clip_map(items: Dict[str, str], cap: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in items.items():
        k_clean = (k or "").strip()[:MAX_ITEM_LEN]
        v_clean = (v or "").strip()[:MAX_ITEM_LEN]
        if not k_clean or not v_clean:
            continue
        out[k_clean] = v_clean
        if len(out) >= cap:
            break
    return out
