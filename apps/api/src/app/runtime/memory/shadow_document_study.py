"""LLM agents and deterministic persistence for shadow document study."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.document_memory_staging import (
    DocumentMemorySnapshot,
    GlossaryTerm,
    MemoryCandidateProjectBinding,
    MemoryExtractionCandidate,
)
from app.models.memory_scope import MemoryCandidateScope, MemoryScope
from app.models.project import Project
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.shadow_study_prompts import (
    document_memory_prompt,
)
from app.services.glossary_service import GlossaryService


SHADOW_STUDY_BATCH_SIZE = 2
MAX_LEDGER_ITEMS = 60
MAX_GLOSSARY_ITEMS = 80


class ShadowScreeningOutput(BaseModel):
    decision: Literal["study", "skip", "needs_review"]
    reason: str = Field(default="", max_length=600)
    document_kind: str = Field(default="unknown", max_length=80)


class ShadowStudyItem(BaseModel):
    operation: Literal["new", "extend_existing"] = "new"
    existing_candidate_id: UUID | None = None
    candidate_type: Literal["term", "description", "relationship", "rule", "constraint", "procedure", "decision"]
    subject: str = Field(min_length=1, max_length=200)
    content: dict[str, Any] = Field(default_factory=dict)
    scope_candidate: Literal["global", "project", "multi_project", "scoped", "unknown"] = "unknown"
    project_keys: list[str] = Field(default_factory=list, max_length=20)
    scope_keys: list[str] = Field(default_factory=list, max_length=20)
    evidence_section_ids: list[str] = Field(default_factory=list, max_length=8)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    extraction_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ShadowStudyOutput(BaseModel):
    items: list[ShadowStudyItem] = Field(default_factory=list, max_length=24)


class ShadowDocumentStudyAgent:
    """Hard-coded prompting over the standard structured LLM transport."""

    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def _prompt(self, stage: Literal["screening", "study"]) -> str:
        config = await self._structured.role_service.get_role_config(SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR)
        return document_memory_prompt(config.get("extras"), stage=stage)

    async def screen(
        self,
        *,
        document: dict[str, Any],
        sample_sections: Sequence[dict[str, Any]],
        tenant_id: UUID,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> ShadowScreeningOutput:
        result = await self._structured.invoke(
            role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
            system_prompt=await self._prompt("screening"),
            payload={"document": document, "sample_sections": list(sample_sections)},
            schema=ShadowScreeningOutput,
            tenant_id=tenant_id,
            use_default_model=True,
            agent_execution_id=agent_execution_id,
            trace_parent_entity_type="agent_execution",
            trace_parent_entity_id=agent_execution_id,
            event_sink=event_sink,
        )
        return result.value

    async def study(
        self,
        *,
        document: dict[str, Any],
        sections: Sequence[dict[str, Any]],
        candidate_ledger: Sequence[dict[str, Any]],
        glossary: Sequence[dict[str, Any]],
        projects: Sequence[dict[str, Any]],
        scopes: Sequence[dict[str, Any]] = (),
        tenant_id: UUID,
        agent_execution_id: str | None = None,
        event_sink: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> ShadowStudyOutput:
        result = await self._structured.invoke(
            role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
            system_prompt=await self._prompt("study"),
            payload={
                "document": document,
                "sections": list(sections),
                "candidate_ledger": list(candidate_ledger),
                "glossary": list(glossary),
                "project_catalog": list(projects),
                "scope_catalog": list(scopes),
            },
            schema=ShadowStudyOutput,
            tenant_id=tenant_id,
            use_default_model=True,
            agent_execution_id=agent_execution_id,
            trace_parent_entity_type="agent_execution",
            trace_parent_entity_id=agent_execution_id,
            event_sink=event_sink,
        )
        return result.value


class ShadowDocumentStudyService:
    """State machine and persistence boundary for a single document snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_snapshot(self, *, document_id: UUID, checksum: str, visibility_tenant_id: UUID | None) -> DocumentMemorySnapshot:
        row = (await self._session.execute(select(DocumentMemorySnapshot).where(
            DocumentMemorySnapshot.document_id == document_id,
            DocumentMemorySnapshot.canonical_checksum == checksum,
        ))).scalar_one_or_none()
        if row is None:
            row = DocumentMemorySnapshot(
                document_id=document_id, canonical_checksum=checksum, visibility_tenant_id=visibility_tenant_id, status="queued",
                metrics={"next_section": 0, "shadow_study": True},
            )
            self._session.add(row)
            await self._session.flush()
        elif row.status == "backfilled":
            row.status = "queued"
            row.metrics = {**dict(row.metrics or {}), "next_section": 0, "shadow_study": True, "reused_backfill": True}
        return row

    async def ledger(self, snapshot_id: UUID) -> list[dict[str, Any]]:
        rows = (await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot_id,
            MemoryExtractionCandidate.resolution_status.not_in(("rejected", "stale")),
        ).order_by(MemoryExtractionCandidate.ordinal.desc()).limit(MAX_LEDGER_ITEMS))).scalars().all()
        return [{
            "id": str(row.id), "type": row.candidate_type, "subject": row.subject,
            "content": dict(row.content or {}), "scope_candidate": row.scope_candidate,
            "evidence_section_ids": list(row.evidence_section_ids or []),
        } for row in reversed(rows)]

    async def glossary_context(self, *, visibility_tenant_id: UUID | None) -> list[dict[str, Any]]:
        rows = (await self._session.execute(GlossaryService.published_terms_query()
            .order_by(GlossaryTerm.canonical_term)
            .limit(MAX_GLOSSARY_ITEMS))).scalars().all()
        return [{"term": term.canonical_term, "aliases": list(term.aliases or [])} for term in rows]

    async def project_catalog(self) -> tuple[dict[str, Project], list[dict[str, Any]]]:
        rows = list((await self._session.execute(select(Project).where(
            Project.is_active.is_(True),
        ).order_by(Project.name))).scalars().all())
        return (
            {project.key.strip().lower(): project for project in rows},
            [{"key": project.key, "name": project.name, "aliases": list(project.aliases or [])} for project in rows],
        )

    async def scope_catalog(self) -> tuple[dict[str, MemoryScope], list[dict[str, Any]]]:
        rows = list((await self._session.execute(select(MemoryScope).order_by(
            MemoryScope.scope_type, MemoryScope.key,
        ))).scalars().all())
        return (
            {scope.key: scope for scope in rows},
            [{"key": scope.key, "type": scope.scope_type, "name": scope.name,
              "aliases": list(scope.aliases or []), "is_all": scope.is_all} for scope in rows],
        )

    async def persist_batch(
        self,
        *,
        snapshot: DocumentMemorySnapshot,
        items: Sequence[ShadowStudyItem],
        section_ids: set[str],
        projects_by_key: dict[str, Project],
        scopes_by_key: dict[str, MemoryScope] | None = None,
    ) -> dict[str, int]:
        known = {UUID(item["id"]): item for item in await self.ledger(snapshot.id)}
        maximum = (await self._session.execute(select(func.max(MemoryExtractionCandidate.ordinal)).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
        ))).scalar_one_or_none()
        next_ordinal = int(maximum if maximum is not None else -1) + 1
        counts = {"created": 0, "extended": 0, "rejected": 0}
        expanded: list[ShadowStudyItem] = []
        for item in items:
            if item.candidate_type == "term":
                definition = str(item.content.get("definition") or "").strip()
                # Older operator prompts still emit a definition inside a term.
                # Preserve it as an independent, scoped knowledge candidate.
                if definition:
                    expanded.append(item.model_copy(update={
                        "candidate_type": "description", "content": {"summary": definition, "details": ""},
                        "aliases": [], "operation": "new", "existing_candidate_id": None,
                    }))
                item = item.model_copy(update={"content": {}, "scope_candidate": "unknown", "project_keys": [], "scope_keys": []})
            expanded.append(item)
        for item in expanded:
            evidence = list(dict.fromkeys(value for value in item.evidence_section_ids if value in section_ids))
            if not evidence:
                counts["rejected"] += 1
                continue
            if item.operation == "extend_existing":
                if item.existing_candidate_id not in known:
                    counts["rejected"] += 1
                    continue
                row = await self._session.get(MemoryExtractionCandidate, item.existing_candidate_id)
                if row is None:
                    counts["rejected"] += 1
                    continue
                row.evidence_section_ids = list(dict.fromkeys([*(row.evidence_section_ids or []), *evidence]))
                row.aliases = _unique([*(row.aliases or []), *item.aliases])
                counts["extended"] += 1
                continue
            subject = _normalized(item.subject)
            if not subject:
                counts["rejected"] += 1
                continue
            proposed_scope_keys = list(dict.fromkeys(
                value.strip().lower() for value in [*item.scope_keys, *(f"project.{key}" for key in item.project_keys)]
                if value.strip()
            ))
            unresolved_scopes = any(key not in (scopes_by_key or {}) for key in proposed_scope_keys)
            proposed_scope = item.scope_candidate
            if (proposed_scope == "global" and proposed_scope_keys) or (
                proposed_scope == "scoped" and (not proposed_scope_keys or unresolved_scopes)
            ):
                proposed_scope = "unknown"
            row = MemoryExtractionCandidate(
                snapshot_id=snapshot.id, ordinal=next_ordinal, candidate_type=item.candidate_type,
                visibility_tenant_id=snapshot.visibility_tenant_id,
                subject=item.subject.strip()[:200], normalized_subject=subject,
                content=dict(item.content or {}), content_text=json.dumps(item.content, ensure_ascii=False, sort_keys=True),
                evidence_section_ids=evidence, aliases=_unique(item.aliases),
                extraction_confidence=item.extraction_confidence,
                scope_candidate=None if item.candidate_type == "term" else proposed_scope,
                resolution_status="extracted", resolution_method="llm_suggestion",
            )
            next_ordinal += 1
            self._session.add(row)
            await self._session.flush()
            for key in dict.fromkeys(value.strip().lower() for value in item.project_keys if value.strip()):
                project = projects_by_key.get(key)
                if project is None:
                    continue
                self._session.add(MemoryCandidateProjectBinding(
                    candidate_id=row.id, project_id=project.id, role="applies_to", status="suggested",
                    method="llm_suggestion", confidence=item.extraction_confidence,
                ))
            for key in proposed_scope_keys:
                scope = (scopes_by_key or {}).get(key)
                if scope is None:
                    continue
                self._session.add(MemoryCandidateScope(
                    candidate_id=row.id, scope_id=scope.id, role="applies_to", status="suggested",
                    method="llm_suggestion", confidence=item.extraction_confidence,
                ))
            counts["created"] += 1
        return counts

    async def finalize(self, snapshot: DocumentMemorySnapshot) -> dict[str, int]:
        candidates = list((await self._session.execute(select(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.snapshot_id == snapshot.id,
            MemoryExtractionCandidate.resolution_status == "extracted",
        ))).scalars().all())
        for candidate in candidates:
            candidate.resolution_status = "needs_review"
        snapshot.status = "conflict_checking"
        snapshot.metrics = {**dict(snapshot.metrics or {}), "candidates": len(candidates), "ready_at": datetime.now(timezone.utc).isoformat()}
        return {"candidates": len(candidates)}


def _normalized(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())[:200]


def _unique(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = " ".join(str(raw or "").strip().split())[:255]
        normalized = value.casefold()
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result
