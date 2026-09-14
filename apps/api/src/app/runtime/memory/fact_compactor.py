"""LLM-assisted normalization of extracted fact candidates.

The compactor may merge equivalent wording, but persistence and confirmation
remain deterministic in FactReconciler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.decisions import JOURNAL_CANDIDATE_IDS, MemoryDecision


class _CompactedFact(BaseModel):
    scope: str
    subject: str
    value: str
    source_candidate_indexes: list[int] = Field(default_factory=list)
    action: Literal["add", "rewrite", "merge", "supersede", "mark_conflict", "discard"] = "add"
    target_current_indexes: list[int] = Field(default_factory=list)


class _CompactionOutput(BaseModel):
    facts: list[_CompactedFact] = Field(default_factory=list)


@dataclass(frozen=True)
class FactCompactionResult:
    facts: list[FactDTO]
    decisions: list[MemoryDecision]
    error_code: str | None = None


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
        return (await self.compact_with_decisions(
            candidates=candidates, current_facts=current_facts, user_id=user_id,
            tenant_id=tenant_id, chat_id=chat_id, sandbox_overrides=sandbox_overrides,
            event_sink=event_sink, agent_execution_id=agent_execution_id,
        )).facts

    async def compact_with_decisions(
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
    ) -> FactCompactionResult:
        if not candidates:
            return FactCompactionResult([], [])
        # Exact user/tenant matches only add independent evidence and do not
        # need semantic interpretation.
        exact: list[FactDTO] = []
        semantic: list[FactDTO] = []
        decisions: list[MemoryDecision] = []
        for candidate in candidates:
            if candidate.scope.value in {"user", "tenant"} and any(
                current.scope == candidate.scope
                and current.kind == candidate.kind
                and current.subject == candidate.subject
                and _normalized(current.value) == _normalized(candidate.value)
                for current in current_facts
            ):
                exact.append(candidate)
                decisions.append(MemoryDecision("fact_compactor", "compaction", "accepted", "exact_match", (candidate,), action="merge"))
            else:
                semantic.append(candidate)
        if not semantic:
            return FactCompactionResult(exact, decisions)
        payload = {
            "stages": ["user", "tenant", "glossary"],
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
            decisions.extend(MemoryDecision("fact_compactor", "compaction", "accepted", "compactor_fallback", (item,)) for item in semantic)
            return FactCompactionResult([*exact, *semantic], decisions, "compactor_call_failed")
        except Exception:
            decisions.extend(MemoryDecision("fact_compactor", "compaction", "accepted", "compactor_fallback", (item,)) for item in semantic)
            return FactCompactionResult([*exact, *semantic], decisions, "compactor_unexpected_error")
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
                decisions.append(MemoryDecision("fact_compactor", "compaction", "skipped", "invalid_source_indexes"))
                continue
            # The compactor is allowed to discard a candidate only when it
            # explicitly references it.  A partial/invalid LLM response must
            # not silently turn evidenced extractor output into data loss.
            represented_candidate_indexes.update(source_indexes)
            if output.action == "discard":
                decisions.append(MemoryDecision("fact_compactor", "compaction", "rejected", "discarded_by_compactor", tuple(matches), action=output.action))
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
            term_aliases: list[str] = []
            seen_term_aliases: set[str] = set()
            for item in matches:
                for raw_alias in item.metadata.get("aliases", []) if isinstance(item.metadata, dict) else []:
                    alias = " ".join(str(raw_alias or "").strip().split())[:120]
                    if alias and alias.casefold() not in seen_term_aliases:
                        seen_term_aliases.add(alias.casefold())
                        term_aliases.append(alias)
            metadata["aliases"] = term_aliases
            merged_ids = [candidate_id for item in matches for candidate_id in item.metadata.get(JOURNAL_CANDIDATE_IDS, []) if isinstance(candidate_id, str)]
            metadata[JOURNAL_CANDIDATE_IDS] = merged_ids
            compacted_fact = FactDTO(
                scope=base.scope,
                subject=output.subject.strip().lower()[:200] or base.subject,
                value=output.value.strip()[:500] or base.value,
                source=base.source,
                tenant_id=base.tenant_id,
                owner_type=base.owner_type,
                owner_id=base.owner_id,
                kind=base.kind,
                metadata=metadata,
                confidence=max(item.confidence for item in matches),
            )
            compacted.append(compacted_fact)
            decisions.append(MemoryDecision(
                "fact_compactor", "compaction",
                "conflict" if output.action == "mark_conflict" else "accepted",
                "compaction_resolved", tuple(matches), action=output.action,
            ))
        untouched = [
            candidate
            for index, candidate in enumerate(semantic)
            if index not in represented_candidate_indexes
        ]
        decisions.extend(MemoryDecision("fact_compactor", "compaction", "accepted", "unrepresented_passthrough", (item,)) for item in untouched)
        return FactCompactionResult([*exact, *compacted, *untouched], decisions)


def item_to_payload(item: FactDTO, index: int | None = None) -> dict[str, Any]:
    result = {
        "scope": item.scope.value,
        "kind": item.kind,
        "subject": item.subject,
        "value": item.value,
        "id": str(item.id) if index is None else None,
    }
    if index is not None:
        result["index"] = index
    return result


def _normalized(value: str) -> str:
    return " ".join((value or "").casefold().split())
