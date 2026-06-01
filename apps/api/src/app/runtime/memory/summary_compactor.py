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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet
from app.services.system_llm_role_service import SystemLLMRoleService

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
    # Optional v2 delta fields. If absent, we fall back to legacy facets above.
    new_goals: List[str] = Field(default_factory=list)
    completed_goals: List[str] = Field(default_factory=list)
    new_entities: Dict[str, str] = Field(default_factory=dict)
    updated_entities: Dict[str, str] = Field(default_factory=dict)
    resolved_questions: List[str] = Field(default_factory=list)
    new_questions: List[str] = Field(default_factory=list)


class SummaryCompactor:
    """Single-call structured summarizer."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self._role_service = SystemLLMRoleService(session)
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
        sandbox_overrides: Optional[dict] = None,
        llm_event_callback: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
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
                sandbox_overrides=sandbox_overrides,
                fallback_factory=lambda _raw: _LLMSummaryOutput(),
            )
            out = result.value
        except StructuredCallError as exc:
            logger.warning("SummaryCompactor structured call failed: %s", exc)
            return self._fallback(previous, turn_number)
        except Exception as exc:  # noqa: BLE001 — never break the turn
            logger.warning("SummaryCompactor unexpected error: %s", exc)
            return self._fallback(previous, turn_number)
        if llm_event_callback is not None:
            try:
                await llm_event_callback(
                    {
                        "role": SystemLLMRoleType.SUMMARY_COMPACTOR.value,
                        "model": result.model,
                        "messages": result.request_messages,
                        "params": result.request_params,
                        "response": result.raw_response,
                        "duration_ms": result.duration_ms,
                    }
                )
            except Exception:
                logger.debug("SummaryCompactor llm_event_callback failed", exc_info=True)

        role_extras: dict = {}
        try:
            role_config = await self._role_service.get_role_config(SystemLLMRoleType.SUMMARY_COMPACTOR)
            maybe_extras = role_config.get("extras")
            if isinstance(maybe_extras, dict):
                role_extras = maybe_extras
        except Exception:
            role_extras = {}
        policy = _resolve_summary_policy(role_extras, sandbox_overrides)

        merged = _merge_summary(previous=previous, out=out, policy=policy)
        return SummaryDTO(
            chat_id=previous.chat_id,
            goals=merged["goals"],
            done=merged["done"],
            entities=merged["entities"],
            open_questions=merged["open_questions"],
            raw_tail=previous.raw_tail,  # writer maintains this
            last_updated_turn=turn_number,
        )

    # ------------------------------------------------------------ helpers ---

    @staticmethod
    def _fallback(previous: SummaryDTO, turn_number: int) -> SummaryDTO:
        """Keep previous structured fields verbatim, bump turn only."""
        copy = deepcopy(previous)
        copy.last_updated_turn = turn_number
        return copy


def _clip_list(items: List[str], cap: int, *, max_item_len: int = MAX_ITEM_LEN) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in items:
        v = (raw or "").strip()[:max_item_len]
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= cap:
            break
    return out


def _clip_map(items: Dict[str, str], cap: int, *, max_item_len: int = MAX_ITEM_LEN) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in items.items():
        k_clean = (k or "").strip()[:max_item_len]
        v_clean = (v or "").strip()[:max_item_len]
        if not k_clean or not v_clean:
            continue
        out[k_clean] = v_clean
        if len(out) >= cap:
            break
    return out


def _resolve_summary_policy(role_extras: Optional[dict], sandbox_overrides: Optional[dict]) -> dict:
    cfg = dict(
        max_goals=MAX_GOALS,
        max_done=MAX_DONE,
        max_entities=MAX_ENTITIES,
        max_open_questions=MAX_OPEN_QUESTIONS,
        max_item_len=MAX_ITEM_LEN,
    )
    overrides = sandbox_overrides or {}
    memory = overrides.get("memory") if isinstance(overrides, dict) else None
    compact = overrides.get("summary_compactor") if isinstance(overrides, dict) else None
    for source in (role_extras, memory, compact):
        if not isinstance(source, dict):
            continue
        for key in ("max_goals", "max_done", "max_entities", "max_open_questions", "max_item_len"):
            val = source.get(key)
            if isinstance(val, int) and val > 0:
                cfg[key] = val
    return cfg


def _merge_summary(*, previous: SummaryDTO, out: _LLMSummaryOutput, policy: dict) -> dict:
    max_item_len = int(policy["max_item_len"])

    prev_goals = _clip_list(list(previous.goals or []), 10_000, max_item_len=max_item_len)
    prev_done = _clip_list(list(previous.done or []), 10_000, max_item_len=max_item_len)
    prev_questions = _clip_list(list(previous.open_questions or []), 10_000, max_item_len=max_item_len)
    prev_entities = _clip_map(dict(previous.entities or {}), 10_000, max_item_len=max_item_len)

    # Delta path (preferred)
    if (
        out.new_goals
        or out.completed_goals
        or out.new_entities
        or out.updated_entities
        or out.resolved_questions
        or out.new_questions
    ):
        normalized_completed = {x.lower() for x in _clip_list(out.completed_goals, 10_000, max_item_len=max_item_len)}
        goals = [g for g in prev_goals if g.lower() not in normalized_completed]
        goals.extend(_clip_list(out.new_goals, 10_000, max_item_len=max_item_len))
        goals = _clip_list(goals, policy["max_goals"], max_item_len=max_item_len)

        done = list(prev_done)
        done.extend(_clip_list(out.completed_goals, 10_000, max_item_len=max_item_len))
        done = _clip_list(done, policy["max_done"], max_item_len=max_item_len)

        entities = dict(prev_entities)
        entities.update(_clip_map(out.new_entities, 10_000, max_item_len=max_item_len))
        entities.update(_clip_map(out.updated_entities, 10_000, max_item_len=max_item_len))
        entities = _clip_map(entities, policy["max_entities"], max_item_len=max_item_len)

        resolved = {x.lower() for x in _clip_list(out.resolved_questions, 10_000, max_item_len=max_item_len)}
        questions = [q for q in prev_questions if q.lower() not in resolved]
        questions.extend(_clip_list(out.new_questions, 10_000, max_item_len=max_item_len))
        questions = _clip_list(questions, policy["max_open_questions"], max_item_len=max_item_len)

        return {
            "goals": goals,
            "done": done,
            "entities": entities,
            "open_questions": questions,
        }

    # Legacy full-state output path
    return {
        "goals": _clip_list(out.goals, policy["max_goals"], max_item_len=max_item_len),
        "done": _clip_list(out.done, policy["max_done"], max_item_len=max_item_len),
        "entities": _clip_map(out.entities, policy["max_entities"], max_item_len=max_item_len),
        "open_questions": _clip_list(out.open_questions, policy["max_open_questions"], max_item_len=max_item_len),
    }
