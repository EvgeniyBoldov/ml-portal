"""Evidence-only feedback for document-derived semantic memory."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemEvaluation, MemoryItemSource
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall


class _MemoryEvaluationOutput(BaseModel):
    outcome: Literal["confirmed", "contradicted", "insufficient", "irrelevant"]
    reason: str = Field(default="", max_length=1000)
    evidence_hit_indexes: list[int] = Field(default_factory=list)


@dataclass(frozen=True)
class MemoryEvaluationDecision:
    outcome: str
    reason: str
    evidence_refs: list[dict[str, Any]]


class MemoryEvidenceEvaluator:
    """LLM comparison that can change trust, never semantic content."""

    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def evaluate(
        self, *, item: MemoryItem, evidence: Sequence[dict[str, Any]], tenant_id: UUID,
        content: dict[str, Any] | None = None,
    ) -> MemoryEvaluationDecision:
        bounded = list(evidence)[:8]
        result = await self._structured.invoke(
            role=SystemLLMRoleType.MEMORY_EVALUATOR,
            payload={
                "memory_item": {
                    "id": str(item.id), "type": item.item_type, "subject": item.subject,
                    "content": content if content is not None else item.content,
                    "state": item.state, "confidence": item.confidence,
                },
                "evidence": bounded,
            },
            schema=_MemoryEvaluationOutput,
            tenant_id=tenant_id,
        )
        refs = [
            _evidence_ref(bounded[index]) for index in result.value.evidence_hit_indexes
            if isinstance(index, int) and 0 <= index < len(bounded)
        ]
        return MemoryEvaluationDecision(
            outcome=result.value.outcome,
            reason=result.value.reason.strip()[:1000],
            evidence_refs=refs,
        )


class MemoryEvidenceFeedbackService:
    """Idempotently records a decision and applies its strictly limited effect."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def already_evaluated(self, *, memory_item_id: UUID, tool_call_id: str) -> bool:
        return (await self._session.execute(select(MemoryItemEvaluation.id).where(
            MemoryItemEvaluation.memory_item_id == memory_item_id,
            MemoryItemEvaluation.tool_call_id == tool_call_id,
        ))).scalar_one_or_none() is not None

    async def apply(
        self, *, item: MemoryItem, claim: MemoryClaim, tool_call_id: str,
        decision: MemoryEvaluationDecision,
    ) -> tuple[bool, list[UUID]]:
        if await self.already_evaluated(memory_item_id=item.id, tool_call_id=tool_call_id):
            return False, []
        self._session.add(MemoryItemEvaluation(
            memory_item_id=item.id, tool_call_id=tool_call_id, outcome=decision.outcome,
            reason=decision.reason, evidence_refs=decision.evidence_refs,
        ))
        document_ids: list[UUID] = []
        if decision.outcome == "confirmed":
            item.last_verified_at = datetime.now(timezone.utc)
        elif decision.outcome == "contradicted":
            # Contradiction belongs to the exact claim recalled by this user.
            # A tenant-local source must not downgrade the company identity.
            claim.state = "conflict"
            if claim.visibility_tenant_id is None:
                item.state = "uncertain"
            document_ids = [claim.document_id]
        await self._session.flush()
        return True, list(dict.fromkeys(document_ids))


def bounded_document_evidence(value: Any) -> list[dict[str, Any]]:
    """Prepare transient, bounded RAG hits; raw tool payload is never persisted."""
    hits = value.get("hits") if isinstance(value, dict) else None
    if not isinstance(hits, list):
        return []
    result: list[dict[str, Any]] = []
    for hit in hits[:8]:
        if not isinstance(hit, dict):
            continue
        text = str(hit.get("text") or hit.get("excerpt") or hit.get("content") or "").strip()
        if not text:
            continue
        result.append({
            "document_id": str(hit.get("artifact_id") or hit.get("document_id") or ""),
            "label": str(hit.get("source_name") or hit.get("title") or "")[:255],
            "text": text[:3000],
        })
    return result


def _evidence_ref(hit: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in {
        "document_id": str(hit.get("document_id") or ""),
        "label": str(hit.get("label") or "")[:255],
    }.items() if value}
