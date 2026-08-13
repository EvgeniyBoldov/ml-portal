"""LLM-assisted normalization of extracted fact candidates.

The compactor may merge equivalent wording, but persistence and confirmation
remain deterministic in FactReconciler.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.memory.dto import FactDTO


class _CompactedFact(BaseModel):
    scope: str
    subject: str
    value: str
    source_candidate_indexes: list[int] = Field(default_factory=list)


class _CompactionOutput(BaseModel):
    facts: list[_CompactedFact] = Field(default_factory=list)


class FactCompactor:
    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def compact(
        self,
        *,
        candidates: Sequence[FactDTO],
        current_facts: Sequence[FactDTO],
        user_id: UUID | None,
        tenant_id: UUID | None,
        chat_id: UUID | None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
    ) -> list[FactDTO]:
        if not candidates:
            return []
        payload = {
            "candidates": [item_to_payload(item, index) for index, item in enumerate(candidates)],
            "current_facts": [item_to_payload(item) for item in current_facts],
        }
        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.FACT_COMPACTOR,
                payload=payload,
                schema=_CompactionOutput,
                user_id=user_id,
                tenant_id=tenant_id,
                chat_id=chat_id,
                event_sink=event_sink,
                fallback_factory=lambda _raw: _CompactionOutput(),
            )
        except StructuredCallError:
            return list(candidates)
        except Exception:
            return list(candidates)
        compacted: list[FactDTO] = []
        for output in result.value.facts:
            matches = [candidates[index] for index in output.source_candidate_indexes if 0 <= index < len(candidates)]
            if not matches:
                continue
            base = matches[0]
            evidence: list[dict[str, Any]] = []
            seen_evidence: set[tuple[str, str]] = set()
            for item in matches:
                for raw in item.metadata.get("evidence", []) if isinstance(item.metadata, dict) else []:
                    if not isinstance(raw, dict):
                        continue
                    key = (str(raw.get("source_type") or ""), str(raw.get("source_ref") or ""))
                    if not all(key) or key in seen_evidence:
                        continue
                    seen_evidence.add(key)
                    evidence.append(dict(raw))
            metadata = dict(base.metadata)
            metadata["evidence"] = evidence
            aliases: list[str] = []
            seen_aliases: set[str] = set()
            for item in matches:
                for raw_alias in item.metadata.get("project_aliases", []) if isinstance(item.metadata, dict) else []:
                    alias = " ".join(str(raw_alias or "").strip().split())[:120]
                    if alias and alias.casefold() not in seen_aliases:
                        seen_aliases.add(alias.casefold())
                        aliases.append(alias)
            metadata["project_aliases"] = aliases
            compacted.append(FactDTO(
                scope=base.scope,
                subject=output.subject.strip().lower()[:200] or base.subject,
                value=output.value.strip()[:500] or base.value,
                source=base.source,
                tenant_id=base.tenant_id,
                project_id=base.project_id,
                metadata=metadata,
                confidence=max(item.confidence for item in matches),
            ))
        return compacted or list(candidates)


def item_to_payload(item: FactDTO, index: int | None = None) -> dict[str, Any]:
    result = {"scope": item.scope.value, "subject": item.subject, "value": item.value}
    if index is not None:
        result["index"] = index
    return result
