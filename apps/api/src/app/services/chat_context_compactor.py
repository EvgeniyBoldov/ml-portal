"""Bounded LLM proposal generator for non-deterministic chat context."""
from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.services.chat_context_contracts import (
    ChatContextOperation, DecisionPayload, GoalPayload, RecentAnchorPayload,
)

logger = get_logger(__name__)


class _CompactionOperationBase(BaseModel):
    action: Literal["add", "update"]
    item_key: str = Field(min_length=1, max_length=255)
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class _GoalCompactionOperation(_CompactionOperationBase):
    kind: Literal["goal"]
    payload: GoalPayload


class _DecisionCompactionOperation(_CompactionOperationBase):
    kind: Literal["decision"]
    payload: DecisionPayload


class _AnchorCompactionOperation(_CompactionOperationBase):
    kind: Literal["recent_anchor"]
    payload: RecentAnchorPayload


_CompactionOperation = Annotated[
    Union[_GoalCompactionOperation, _DecisionCompactionOperation, _AnchorCompactionOperation],
    Field(discriminator="kind"),
]


class _CompactionOutput(BaseModel):
    operations: list[_CompactionOperation] = Field(default_factory=list, max_length=5)


class ChatContextCompactor:
    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def propose(
        self, *, snapshot: dict[str, Any], recent_dialogue: list[dict[str, str]],
        outcome: dict[str, Any], valid_source_ids: list[str], expected_revision: int,
        chat_id: str, user_id: str, tenant_id: str,
    ) -> list[ChatContextOperation]:
        allowed = {value for value in valid_source_ids if value}
        if not allowed:
            return []
        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.CHAT_CONTEXT_COMPACTOR,
                payload={"snapshot": snapshot, "recent_dialogue": recent_dialogue[-8:], "outcome": outcome, "valid_source_ids": sorted(allowed)},
                schema=_CompactionOutput, chat_id=UUID(chat_id), user_id=UUID(user_id), tenant_id=UUID(tenant_id),
                fallback_factory=lambda _raw: _CompactionOutput(),
            )
        except Exception:
            logger.warning("chat_context_compaction_proposal_failed", exc_info=True, extra={"chat_id": chat_id})
            return []
        operations: list[ChatContextOperation] = []
        for item in result.value.operations:
            if not item.source_ids or not set(item.source_ids).issubset(allowed):
                continue
            payload = _bounded_payload(item.payload.model_dump(mode="json"))
            item_key, action = _canonical_key(item.kind, item.action, item.source_ids, payload)
            operations.append(ChatContextOperation(
                action=action, kind=item.kind, item_key=item_key,
                payload={**payload, "trust_class": "compacted"}, source_ids=item.source_ids,
                expected_revision=expected_revision, confidence=0.5,
            ))
        return operations


def _bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or len(key) > 80:
            continue
        if isinstance(value, str):
            result[key] = value[:600]
        elif isinstance(value, (bool, int, float)):
            result[key] = value
        elif isinstance(value, list):
            result[key] = [str(item)[:120] for item in value[:10]]
    return result


def _canonical_key(kind: str, action: str, source_ids: list[str], payload: dict[str, Any]) -> tuple[str, str]:
    if kind == "goal":
        return "active_goal", "update"
    if kind == "recent_anchor":
        return "recent_anchor", "update"
    fingerprint = hashlib.sha256(repr((sorted(source_ids), sorted(payload.items()))).encode()).hexdigest()[:20]
    return f"decision:{fingerprint}", "add"
