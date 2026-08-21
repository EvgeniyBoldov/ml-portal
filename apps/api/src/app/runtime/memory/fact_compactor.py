"""LLM-assisted normalization of extracted fact candidates.

The compactor may merge equivalent wording, but persistence and confirmation
remain deterministic in FactReconciler.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, Sequence
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
    action: Literal["add", "rewrite", "merge", "supersede", "mark_conflict", "discard"] = "add"
    target_current_indexes: list[int] = Field(default_factory=list)


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
        sandbox_overrides: dict[str, Any] | None = None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
        agent_execution_id: str | None = None,
    ) -> list[FactDTO]:
        if not candidates:
            return []
        # Exact user/tenant matches only add independent evidence and do not
        # need semantic interpretation. Project candidates never use this
        # shortcut: their wording may encode an exception or a revised rule.
        exact: list[FactDTO] = []
        semantic: list[FactDTO] = []
        for candidate in candidates:
            if candidate.scope.value in {"user", "tenant"} and any(
                current.scope == candidate.scope
                and current.kind == candidate.kind
                and current.subject == candidate.subject
                and _normalized(current.value) == _normalized(candidate.value)
                for current in current_facts
            ):
                exact.append(candidate)
            else:
                semantic.append(candidate)
        if not semantic:
            return exact
        payload = {
            "stages": ["user", "tenant", "glossary", "project"],
            "candidates": [item_to_payload(item, index) for index, item in enumerate(semantic)],
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
                sandbox_overrides=sandbox_overrides,
                event_sink=event_sink,
                agent_execution_id=agent_execution_id,
                fallback_factory=lambda _raw: _CompactionOutput(),
            )
        except StructuredCallError:
            return [*exact, *semantic]
        except Exception:
            return [*exact, *semantic]
        compacted: list[FactDTO] = []
        represented_candidate_indexes: set[int] = set()
        for output in result.value.facts:
            source_indexes = [
                index
                for index in output.source_candidate_indexes
                if 0 <= index < len(semantic)
            ]
            matches = [semantic[index] for index in source_indexes]
            if not matches:
                continue
            # The compactor is allowed to discard a candidate only when it
            # explicitly references it.  A partial/invalid LLM response must
            # not silently turn evidenced extractor output into data loss.
            represented_candidate_indexes.update(source_indexes)
            if output.action == "discard":
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
            metadata["compaction_action"] = output.action
            metadata["compaction_target_ids"] = [
                str(current_facts[index].id)
                for index in output.target_current_indexes
                if 0 <= index < len(current_facts)
            ]
            aliases: list[str] = []
            seen_aliases: set[str] = set()
            for item in matches:
                for raw_alias in item.metadata.get("project_aliases", []) if isinstance(item.metadata, dict) else []:
                    alias = " ".join(str(raw_alias or "").strip().split())[:120]
                    if alias and alias.casefold() not in seen_aliases:
                        seen_aliases.add(alias.casefold())
                        aliases.append(alias)
            metadata["project_aliases"] = aliases
            term_aliases: list[str] = []
            seen_term_aliases: set[str] = set()
            for item in matches:
                for raw_alias in item.metadata.get("aliases", []) if isinstance(item.metadata, dict) else []:
                    alias = " ".join(str(raw_alias or "").strip().split())[:120]
                    if alias and alias.casefold() not in seen_term_aliases:
                        seen_term_aliases.add(alias.casefold())
                        term_aliases.append(alias)
            metadata["aliases"] = term_aliases
            compacted.append(FactDTO(
                scope=base.scope,
                subject=output.subject.strip().lower()[:200] or base.subject,
                value=output.value.strip()[:500] or base.value,
                source=base.source,
                tenant_id=base.tenant_id,
                project_id=base.project_id,
                owner_type=base.owner_type,
                owner_id=base.owner_id,
                kind=base.kind,
                metadata=metadata,
                confidence=max(item.confidence for item in matches),
            ))
        untouched = [
            candidate
            for index, candidate in enumerate(semantic)
            if index not in represented_candidate_indexes
        ]
        return [*exact, *compacted, *untouched]


def item_to_payload(item: FactDTO, index: int | None = None) -> dict[str, Any]:
    result = {
        "scope": item.scope.value,
        "kind": item.kind,
        "subject": item.subject,
        "value": item.value,
        "project_key": str(item.metadata.get("project_key") or "") if isinstance(item.metadata, dict) else "",
        "id": str(item.id) if index is None else None,
    }
    if index is not None:
        result["index"] = index
    return result


def _normalized(value: str) -> str:
    return " ".join((value or "").casefold().split())
