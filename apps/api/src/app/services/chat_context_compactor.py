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
    ChatContextOperation, DecisionPayload, GoalPayload, RecentAnchorPayload, TopicScopePayload, ScopePayload,
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


class FocusCompactionPayload(BaseModel):
    topic: str = Field(default="", max_length=600)
    team_keys: list[str] | None = Field(default=None, max_length=30)
    project_keys: list[str] | None = Field(default=None, max_length=30)


class _TopicCompactionOperation(_CompactionOperationBase):
    kind: Literal["scope"]
    payload: FocusCompactionPayload


_CompactionOperation = Annotated[
    Union[_GoalCompactionOperation, _DecisionCompactionOperation, _AnchorCompactionOperation, _TopicCompactionOperation],
    Field(discriminator="kind"),
]


class _CompactionOutput(BaseModel):
    operations: list[_CompactionOperation] = Field(default_factory=list, max_length=5)


class ChatContextCompactor:
    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._session = session
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def propose(
        self, *, snapshot: dict[str, Any], recent_dialogue: list[dict[str, str]],
        outcome: dict[str, Any], valid_source_ids: list[str], expected_revision: int,
        chat_id: str, user_id: str, tenant_id: str,
    ) -> list[ChatContextOperation]:
        allowed = {value for value in valid_source_ids if value}
        if not allowed:
            return []
        from app.services.memory_scope_catalog import list_memory_scopes
        catalog = [row for row in await list_memory_scopes(self._session) if not row.is_all]
        known = {row.key for row in catalog}
        try:
            config = await self._structured.role_service.get_role_config(SystemLLMRoleType.CHAT_CONTEXT_COMPACTOR)
            prompt = self._structured._compile_role_prompt(config, None, schema=_CompactionOutput) + "\n\n" + FOCUS_COMPACTION_PROMPT
            result = await self._structured.invoke(
                role=SystemLLMRoleType.CHAT_CONTEXT_COMPACTOR,
                system_prompt=prompt,
                payload={"scope_catalog": [{"key": row.key, "name": row.name, "aliases": row.aliases} for row in catalog], "snapshot": snapshot, "recent_dialogue": recent_dialogue[-8:], "outcome": outcome, "valid_source_ids": sorted(allowed)},
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
            if item.kind == "scope":
                previous = snapshot.get("focus") or {}
                payload = focus_compaction_payload(previous, item.payload, known)
                if payload is None:
                    continue
            item_key, action = _canonical_key(item.kind, item.action, item.source_ids, payload)
            operations.append(ChatContextOperation(
                action=action, kind=item.kind, item_key=item_key,
                payload={**payload, "trust_class": "model_inferred"}, source_ids=item.source_ids,
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
    if kind in {"goal", "scope"}:
        return ("active_goal" if kind == "goal" else "current_scope"), "update"
    if kind == "recent_anchor":
        return "recent_anchor", "update"
    fingerprint = hashlib.sha256(repr((sorted(source_ids), sorted(payload.items()))).encode()).hexdigest()[:20]
    return f"decision:{fingerprint}", "add"


FOCUS_COMPACTION_PROMPT = """Сожми рабочий контекст завершённого хода чата.
Верни операции goal, decision, recent_anchor или scope с source_ids из valid_source_ids.
Коррекция фокуса разрешена этим контрактом, даже если старый prompt запрещал её.
Фокус состоит из двух независимых веток: team_keys (кому), project_keys (где).
Используй только точные конкретные ключи из scope_catalog; all запрещён.
Прочитай диалог, включая вопрос агента и подтверждение/ответ пользователя.
Меняй ветку только если пользователь выбрал, уточнил или подтвердил её.
Простое упоминание, пример или неподтверждённый вопрос агента не меняет фокус.
null/отсутствующая ветка сохраняет предыдущий выбор, [] явно очищает ветку.
При смене проекта сохраняй команду, если пользователь её не менял, и наоборот.
Не переписывай подтверждённые решения догадками. Каждый вывод ссылается на evidence.
"""


def focus_compaction_payload(previous: dict[str, Any], proposal: FocusCompactionPayload,
                             known: set[str]) -> dict[str, Any] | None:
    """Preserve untouched branches and validate exact catalog identities."""
    from app.runtime.memory.search import normalize_query_keys
    result = ScopePayload.model_validate(previous).model_dump(mode="json")
    changed = False
    for branch in ("team", "project"):
        values = getattr(proposal, f"{branch}_keys")
        if values is None:
            continue
        try:
            keys = normalize_query_keys(values, branch)
        except ValueError:
            return None
        if not set(keys).issubset(known):
            return None
        result[f"{branch}_keys"] = [key.removeprefix(f"{branch}.") for key in keys]
        result["scope_keys"] = [key for key in result["scope_keys"] if not key.startswith(f"{branch}.")] + keys
        result[f"suppress_{branch}_default"] = not keys
        result["scope_origins"] = {key: origin for key, origin in result["scope_origins"].items() if not key.startswith(f"{branch}.")}
        result["scope_origins"].update({key: "chat_focus" for key in keys})
        changed = True
    if proposal.topic:
        result["topic"] = proposal.topic
    # Pure topic inference must not replace exact scope state.
    result["source"] = "explicit" if changed else "inferred"
    result["scope_revision"] += int(changed)
    return result
