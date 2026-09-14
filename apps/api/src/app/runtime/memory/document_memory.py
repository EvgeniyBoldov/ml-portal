"""Document-derived semantic memory extraction and persistence."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.glossary import GlossaryEntry, GlossaryObservation, GlossaryScope, GlossaryStatus
from app.models.knowledge_entity import KnowledgeEntity, KnowledgeEntitySource
from app.models.memory import MemoryClaim, MemoryItem, MemoryItemSource, MemoryRelation
from app.models.project import Project
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.content_contracts import normalize_memory_content


PROJECT_CONFIDENCE_MIN = 0.85
MAX_DOCUMENT_MEMORY_ITEMS = 24
MEMORY_ITEM_TYPES = {"description", "relationship", "rule", "constraint", "procedure", "decision"}


class _DocumentMemoryCandidate(BaseModel):
    item_type: str
    subject: str
    content: dict[str, Any] = Field(default_factory=dict)
    scope: str | None = None
    project_key: str | None = None
    project_confidence: float = 0.0
    extraction_confidence: float = 0.7
    applicability: dict[str, Any] = Field(default_factory=dict)
    related_project_keys: list[str] = Field(default_factory=list)
    related_entities: list[dict[str, str]] = Field(default_factory=list)
    evidence_section_ids: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    term_kind: str | None = None


class _DocumentMemoryOutput(BaseModel):
    items: list[_DocumentMemoryCandidate] = Field(default_factory=list)


@dataclass(frozen=True)
class DocumentMemoryCandidate:
    item_type: str
    subject: str
    content: dict[str, Any]
    project_key: str | None
    project_confidence: float
    evidence_section_ids: tuple[str, ...]
    extraction_confidence: float = 0.7
    scope: str = "project"
    applicability: dict[str, Any] = field(default_factory=dict)
    related_project_keys: tuple[str, ...] = ()
    related_entities: tuple[tuple[str, str, str], ...] = ()
    aliases: tuple[str, ...] = ()
    term_kind: str | None = None


class DocumentMemoryExtractor:
    """Structured LLM extraction over bounded, addressable canonical sections."""

    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)
        self.rejection_counts: dict[str, int] = {}

    async def extract(
        self,
        *,
        document: dict[str, Any],
        sections: Sequence[dict[str, Any]],
        projects: Sequence[dict[str, Any]],
        tenant_id: UUID,
    ) -> list[DocumentMemoryCandidate]:
        self.rejection_counts = {}
        section_ids = {str(item.get("id") or "") for item in sections}
        candidates: list[DocumentMemoryCandidate] = []
        shortlisted_projects = _shortlist_projects(document, sections, projects)
        for section_group in _logical_section_groups(sections):
            result = await self._structured.invoke(
                role=SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR,
                payload={
                    "document": document,
                    "sections": section_group,
                    "projects": shortlisted_projects,
                    "contract": {
                        "item_types": ["term", *sorted(MEMORY_ITEM_TYPES)],
                        "scopes": ["company", "project"],
                        "project_confidence_min": PROJECT_CONFIDENCE_MIN,
                        "terms_without_project_are_allowed": True,
                        "company_rules_and_procedures_are_allowed": True,
                    },
                },
                schema=_DocumentMemoryOutput,
                tenant_id=tenant_id,
            )
            for item in result.value.items:
                item_type = str(item.item_type or "").strip().lower()
                subject = _normalize_subject(item.subject)
                evidence = tuple(dict.fromkeys(
                    str(section_id) for section_id in item.evidence_section_ids if str(section_id) in section_ids
                ))
                # A document is not presumed project-owned.  If the extractor
                # did not declare a scope, the presence of a project key is
                # the only evidence for project ownership; otherwise retain it
                # as company knowledge.
                scope = str(item.scope or ("project" if item.project_key else "company")).strip().lower()
                if not subject or not evidence or scope not in {"company", "project"}:
                    continue
                if item_type != "term" and item_type not in MEMORY_ITEM_TYPES:
                    continue
                if item_type != "term" and not item.content:
                    continue
                try:
                    content = normalize_memory_content(item_type, dict(item.content or {}))
                except ValueError:
                    # The model may propose a useful-looking but partial
                    # procedure or policy. It is never published as durable
                    # memory without the complete typed contract.
                    self.rejection_counts[item_type] = self.rejection_counts.get(item_type, 0) + 1
                    continue
                if item_type == "relationship" and not (item.related_project_keys or item.related_entities):
                    self.rejection_counts[item_type] = self.rejection_counts.get(item_type, 0) + 1
                    continue
                if item_type != "term" and scope == "project" and not _normalize_project_key(item.project_key):
                    scope = "company"
                candidates.append(DocumentMemoryCandidate(
                    item_type=item_type,
                    subject=subject,
                    content=content,
                    scope=scope,
                    project_key=_normalize_project_key(item.project_key),
                    project_confidence=max(0.0, min(1.0, float(item.project_confidence or 0.0))),
                    extraction_confidence=max(0.0, min(1.0, float(item.extraction_confidence or 0.7))),
                    applicability=dict(item.applicability or {}),
                    related_project_keys=tuple(dict.fromkeys(
                        key for key in (_normalize_project_key(value) for value in item.related_project_keys) if key
                    )),
                    related_entities=tuple(_related_entities(item.related_entities)),
                    evidence_section_ids=evidence,
                    aliases=tuple(_clean_aliases(item.aliases, subject)),
                    term_kind=str(item.term_kind or "").strip().lower() or None,
                ))
                if len(candidates) >= MAX_DOCUMENT_MEMORY_ITEMS:
                    return candidates
        return candidates


class DocumentMemoryService:
    """Applies trusted document candidates without exposing a user-facing revision model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(
        self,
        *,
        document_id: UUID,
        canonical_checksum: str,
        candidates: Sequence[DocumentMemoryCandidate],
        sections: Sequence[dict[str, Any]],
        tenant_id: UUID | None = None,
        document_scope: str = "global",
    ) -> dict[str, int]:
        # `candidates` is a successful extraction snapshot.  Replacing all
        # prior evidence here (including the same checksum) prevents terms or
        # procedures which the new extraction no longer supports from staying
        # active forever.  Extraction itself runs before this method, so an
        # LLM failure never retires the previous snapshot.
        await self._replace_document_snapshot(document_id)
        projects = await self._projects_by_key()
        section_map = {str(item.get("id")): item for item in sections}
        counts = {"memory_items": 0, "glossary_terms": 0, "unresolved_project_items": 0}
        # Terms establish entity identities. Apply them before relationships so
        # the extractor's array order can never decide whether an edge exists.
        ordered_candidates = [item for item in candidates if item.item_type == "term"] + [
            item for item in candidates if item.item_type != "term"
        ]
        for candidate in ordered_candidates:
            project = projects.get(candidate.project_key or "")
            project_resolved = project is not None and candidate.project_confidence >= PROJECT_CONFIDENCE_MIN
            if candidate.item_type == "term":
                if await self._apply_term(
                    candidate=candidate,
                    project=project if project_resolved else None,
                    document_id=document_id,
                    canonical_checksum=canonical_checksum,
                    section_map=section_map,
                    tenant_id=tenant_id,
                    document_scope=document_scope,
                ):
                    counts["glossary_terms"] += 1
                continue
            if candidate.scope == "project" and not project_resolved:
                counts["unresolved_project_items"] += 1
                continue
            if await self._apply_memory_item(
                candidate=candidate,
                project=project if project_resolved else None,
                document_id=document_id,
                canonical_checksum=canonical_checksum,
                section_map=section_map,
                visibility_tenant_id=tenant_id if document_scope == "local" else None,
            ):
                counts["memory_items"] += 1
        await self._session.flush()
        return counts

    async def _replace_document_snapshot(self, document_id: UUID) -> None:
        """Withdraw every derived binding for one document before republishing it.

        A canonical checksum identifies source bytes, not an extraction model
        version.  Keeping same-checksum rows made a forced re-extraction an
        additive operation and left withdrawn knowledge visible.
        """
        await self._withdraw_document_glossary_observations(document_id)
        await self._retire_entity_sources(document_id)
        item_ids = list((await self._session.execute(
            select(MemoryItemSource.memory_item_id).where(
                MemoryItemSource.document_id == document_id,
            )
        )).scalars().all())
        claim_item_ids = list((await self._session.execute(
            select(MemoryClaim.memory_item_id).where(
                MemoryClaim.document_id == document_id,
                MemoryClaim.state == "active",
            )
        )).scalars().all())
        await self._session.execute(
            update(MemoryClaim)
            .where(MemoryClaim.document_id == document_id)
            .where(MemoryClaim.state == "active")
            .values(state="stale")
        )
        await self._session.execute(delete(MemoryItemSource).where(
            MemoryItemSource.document_id == document_id,
        ))
        # Relations are derived from the document snapshot as well.
        await self._session.execute(delete(MemoryRelation).where(MemoryRelation.document_id == document_id))
        for item_id in set([*item_ids, *claim_item_ids]):
            await self._consolidate_item(item_id)

    async def _projects_by_key(self) -> dict[str, Project]:
        rows = await self._session.execute(select(Project).where(Project.is_active.is_(True)))
        return {str(item.key).strip().lower(): item for item in rows.scalars().all()}

    async def _apply_memory_item(
        self,
        *,
        candidate: DocumentMemoryCandidate,
        project: Project | None,
        document_id: UUID,
        canonical_checksum: str,
        section_map: dict[str, dict[str, Any]],
        visibility_tenant_id: UUID | None,
    ) -> bool:
        if candidate.item_type == "relationship" and not (candidate.related_project_keys or candidate.related_entities):
            return False
        try:
            content = normalize_memory_content(candidate.item_type, candidate.content)
        except ValueError:
            return False
        candidate = replace(candidate, content=content)
        normalized = _normalize_subject(candidate.subject)
        scope = candidate.scope
        item_query = select(MemoryItem).where(
            MemoryItem.scope == scope,
            MemoryItem.item_type == candidate.item_type,
            MemoryItem.normalized_subject == normalized,
        )
        item_query = item_query.where(MemoryItem.project_id == project.id) if project else item_query.where(MemoryItem.project_id.is_(None))
        item = (await self._session.execute(item_query)).scalar_one_or_none()
        content_text = _content_text(candidate.content)
        now = datetime.now(timezone.utc)
        if item is None:
            item = MemoryItem(
                scope=scope, item_type=candidate.item_type, project_id=project.id if project else None,
                owner_type="project" if project else "company", owner_id=project.id if project else None,
                applicability=_item_applicability(candidate, project), visibility={"mode": "source"},
                subject=candidate.subject, normalized_subject=normalized,
                content=candidate.content, content_text=content_text, confidence=candidate.extraction_confidence,
                extraction_confidence=candidate.extraction_confidence,
                project_resolution_confidence=candidate.project_confidence,
                source_trust=1.0,
                state="uncertain", last_verified_at=now,
            )
            self._session.add(item)
            await self._session.flush()
        claim_query = select(MemoryClaim).where(
            MemoryClaim.document_id == document_id,
            MemoryClaim.canonical_checksum == canonical_checksum,
            MemoryClaim.scope == scope,
            MemoryClaim.item_type == candidate.item_type,
            MemoryClaim.normalized_subject == normalized,
        )
        claim_query = claim_query.where(MemoryClaim.project_id == project.id) if project else claim_query.where(MemoryClaim.project_id.is_(None))
        claim = (await self._session.execute(claim_query)).scalar_one_or_none()
        if claim is None:
            claim = MemoryClaim(
                memory_item_id=item.id, document_id=document_id, canonical_checksum=canonical_checksum,
                scope=scope, item_type=candidate.item_type, project_id=project.id if project else None,
                visibility_tenant_id=visibility_tenant_id,
                normalized_subject=normalized, content=candidate.content, content_text=content_text,
                evidence_section_ids=list(candidate.evidence_section_ids), confidence=candidate.extraction_confidence,
                extraction_confidence=candidate.extraction_confidence,
                project_resolution_confidence=candidate.project_confidence,
                source_trust=1.0,
                applicability=_item_applicability(candidate, project),
                state="active",
            )
            self._session.add(claim)
        else:
            claim.memory_item_id = item.id
            claim.content = candidate.content
            claim.content_text = content_text
            claim.evidence_section_ids = list(candidate.evidence_section_ids)
            claim.confidence = candidate.extraction_confidence
            claim.extraction_confidence = candidate.extraction_confidence
            claim.project_resolution_confidence = candidate.project_confidence
            claim.source_trust = 1.0
            claim.applicability = _item_applicability(candidate, project)
            claim.visibility_tenant_id = visibility_tenant_id
            claim.state = "active"
        source_added = await self._attach_sources(item, document_id, canonical_checksum, candidate.evidence_section_ids, section_map)
        await self._session.flush()
        await self._consolidate_item(item.id)
        await self._attach_relations(
            item.id, document_id, project, candidate.related_project_keys, candidate.related_entities,
            visibility_tenant_id=visibility_tenant_id,
        )
        return source_added

    async def _attach_relations(
        self, item_id: UUID, document_id: UUID, project: Project | None, related_project_keys: Sequence[str],
        related_entities: Sequence[tuple[str, str, str]],
        visibility_tenant_id: UUID | None,
    ) -> None:
        projects = await self._projects_by_key()
        targets = [project, *(projects.get(key) for key in related_project_keys)]
        for target in {item.id: item for item in targets if item is not None}.values():
            exists = (await self._session.execute(select(MemoryRelation.id).where(
                MemoryRelation.memory_item_id == item_id,
                MemoryRelation.document_id == document_id,
                MemoryRelation.relation_type == "belongs_to_project",
                MemoryRelation.target_type == "project",
                MemoryRelation.target_id == str(target.id),
            ))).scalar_one_or_none()
            if exists is None:
                self._session.add(MemoryRelation(
                    memory_item_id=item_id, document_id=document_id, relation_type="belongs_to_project",
                    target_type="project", target_id=str(target.id),
                ))
        for target_type, target_id, relation_type in related_entities:
            entity = await self._resolve_entity(target_type, target_id, tenant_id=visibility_tenant_id)
            if entity is None:
                continue
            exists = (await self._session.execute(select(MemoryRelation.id).where(
                MemoryRelation.memory_item_id == item_id,
                MemoryRelation.document_id == document_id,
                MemoryRelation.relation_type == relation_type,
                MemoryRelation.target_type == target_type,
                MemoryRelation.target_id == str(entity.id),
            ))).scalar_one_or_none()
            if exists is None:
                self._session.add(MemoryRelation(
                    memory_item_id=item_id, document_id=document_id, relation_type=relation_type,
                    target_type=target_type, target_id=str(entity.id),
                ))

    async def _resolve_entity(self, entity_type: str, raw: str, *, tenant_id: UUID | None) -> KnowledgeEntity | None:
        normalized = _normalize_subject(raw)
        if not normalized:
            return None
        visibility = KnowledgeEntitySource.visibility_tenant_id.is_(None)
        if tenant_id is not None:
            visibility = (KnowledgeEntitySource.visibility_tenant_id.is_(None) | (KnowledgeEntitySource.visibility_tenant_id == tenant_id))
        rows = (await self._session.execute(select(KnowledgeEntity, KnowledgeEntitySource).join(
            KnowledgeEntitySource, KnowledgeEntitySource.entity_id == KnowledgeEntity.id,
        ).where(KnowledgeEntity.entity_type == entity_type, KnowledgeEntity.is_active.is_(True), visibility))).all()
        matched = {
            entity.id: entity for entity, source in rows
            if _normalize_subject(source.canonical_name) == normalized
            or normalized in {_normalize_subject(alias) for alias in source.aliases}
        }
        # Alias collision is an ambiguity, never a license to attach a relation
        # to whichever entity happened to be returned first by PostgreSQL.
        return next(iter(matched.values())) if len(matched) == 1 else None

    async def _upsert_entity(
        self, *, entity_type: str, canonical_name: str, aliases: Sequence[str], project: Project | None,
        document_id: UUID, canonical_checksum: str, visibility_tenant_id: UUID | None,
        evidence_section_ids: Sequence[str],
    ) -> KnowledgeEntity:
        normalized = _normalize_subject(canonical_name)
        row = (await self._session.execute(select(KnowledgeEntity).where(
            KnowledgeEntity.entity_type == entity_type, KnowledgeEntity.normalized_name == normalized,
        ))).scalar_one_or_none()
        if row is None:
            row = KnowledgeEntity(
                entity_type=entity_type, canonical_name=canonical_name, normalized_name=normalized,
            )
            self._session.add(row)
            await self._session.flush()
        else:
            row.is_active = True
        source_query = select(KnowledgeEntitySource).where(
            KnowledgeEntitySource.entity_id == row.id,
            KnowledgeEntitySource.document_id == document_id,
            KnowledgeEntitySource.canonical_checksum == canonical_checksum,
        )
        source_query = source_query.where(KnowledgeEntitySource.project_id == project.id) if project else source_query.where(KnowledgeEntitySource.project_id.is_(None))
        source = (await self._session.execute(source_query)).scalar_one_or_none()
        if source is None:
            self._session.add(KnowledgeEntitySource(
                entity_id=row.id, document_id=document_id, canonical_checksum=canonical_checksum,
                canonical_name=canonical_name, aliases=_clean_aliases(aliases, canonical_name),
                project_id=project.id if project else None, visibility_tenant_id=visibility_tenant_id,
                evidence_section_ids=list(evidence_section_ids),
            ))
        else:
            source.canonical_name = canonical_name
            source.aliases = _clean_aliases(aliases, canonical_name)
            source.visibility_tenant_id = visibility_tenant_id
            source.evidence_section_ids = list(evidence_section_ids)
        await self._session.flush()
        return row

    async def _retire_entity_sources(self, document_id: UUID, *, keep_checksum: str | None = None) -> None:
        query = select(KnowledgeEntitySource.entity_id).where(KnowledgeEntitySource.document_id == document_id)
        if keep_checksum is not None:
            query = query.where(KnowledgeEntitySource.canonical_checksum != keep_checksum)
        entity_ids = set((await self._session.execute(query)).scalars().all())
        if not entity_ids:
            return
        statement = delete(KnowledgeEntitySource).where(KnowledgeEntitySource.document_id == document_id)
        if keep_checksum is not None:
            statement = statement.where(KnowledgeEntitySource.canonical_checksum != keep_checksum)
        await self._session.execute(statement)
        for entity_id in entity_ids:
            entity = (await self._session.execute(select(KnowledgeEntity).where(KnowledgeEntity.id == entity_id))).scalar_one_or_none()
            if entity is not None:
                remaining = (await self._session.execute(select(KnowledgeEntitySource.id).where(
                    KnowledgeEntitySource.entity_id == entity_id,
                ).limit(1))).scalar_one_or_none()
                entity.is_active = remaining is not None

    async def _consolidate_item(self, item_id: UUID) -> None:
        """Publish one current meaning only when active claims agree."""
        item = (await self._session.execute(select(MemoryItem).where(MemoryItem.id == item_id))).scalar_one_or_none()
        if item is None:
            return
        claims = list((await self._session.execute(select(MemoryClaim).where(
            MemoryClaim.memory_item_id == item_id, MemoryClaim.state == "active",
        ).order_by(MemoryClaim.confidence.desc(), MemoryClaim.updated_at.desc()))).scalars().all())
        if not claims:
            item.state = "stale"
            return
        distinct_contents = {claim.content_text for claim in claims}
        winner = claims[0]
        item.content = winner.content
        item.content_text = winner.content_text
        item.confidence = winner.confidence
        item.extraction_confidence = winner.extraction_confidence
        item.project_resolution_confidence = winner.project_resolution_confidence
        item.source_trust = winner.source_trust
        item.last_verified_at = datetime.now(timezone.utc)
        item.state = "active" if len(distinct_contents) == 1 else "uncertain"

    async def _apply_term(
        self,
        *,
        candidate: DocumentMemoryCandidate,
        project: Project | None,
        document_id: UUID,
        canonical_checksum: str,
        section_map: dict[str, dict[str, Any]],
        tenant_id: UUID | None,
        document_scope: str,
    ) -> bool:
        entity_type = candidate.term_kind or "term"
        if entity_type == "service_alias" and project is None:
            entity_type = "service"
        entity_id: str | None = None
        if entity_type in {"service", "system", "environment"}:
            entity = await self._upsert_entity(
                entity_type=entity_type, canonical_name=candidate.subject,
                aliases=candidate.aliases, project=project,
                document_id=document_id, canonical_checksum=canonical_checksum,
                visibility_tenant_id=tenant_id if document_scope == "local" else None,
                evidence_section_ids=candidate.evidence_section_ids,
            )
            entity_id = str(entity.id)
        elif project is not None and entity_type in {"project_alias", "service_alias"}:
            entity_type, entity_id = "project", str(project.id)
        # A legacy nullable unique key can contain duplicate global rows.  Use
        # the oldest canonical row as the stable company-wide glossary entry.
        row = (await self._session.execute(
            select(GlossaryEntry).where(
                GlossaryEntry.scope == GlossaryScope.GLOBAL.value,
                GlossaryEntry.canonical_term == candidate.subject,
                GlossaryEntry.tenant_id.is_(None),
            ).order_by(GlossaryEntry.created_at, GlossaryEntry.id).limit(1)
        )).scalars().first()
        if row is None:
            row = GlossaryEntry(
                scope=GlossaryScope.GLOBAL.value,
                tenant_id=None,
                canonical_term=candidate.subject,
                aliases=list(candidate.aliases),
                entity_type=entity_type,
                entity_id=entity_id,
                project_id=project.id if project is not None else None,
                description=str(candidate.content.get("definition") or candidate.subject),
                status=GlossaryStatus.CONFIRMED.value,
                support_count=0,
                first_confirmed_at=datetime.now(timezone.utc),
                last_confirmed_at=datetime.now(timezone.utc),
            )
            self._session.add(row)
            await self._session.flush()
        else:
            row.is_active = True
            if entity_id is not None:
                row.entity_type = entity_type
                row.entity_id = entity_id
            row.last_confirmed_at = datetime.now(timezone.utc)
        added = 0
        for section_id in candidate.evidence_section_ids:
            source_ref = f"{document_id}:{canonical_checksum}:{section_id}"
            exists = (await self._session.execute(select(GlossaryObservation.id).where(
                GlossaryObservation.entry_id == row.id,
                GlossaryObservation.source_type == "document",
                GlossaryObservation.source_ref == source_ref,
            ))).scalar_one_or_none()
            if exists is None:
                section = section_map[section_id]
                self._session.add(GlossaryObservation(
                    entry_id=row.id, source_type="document", source_ref=source_ref,
                    source_label=str(section.get("label") or section_id)[:255],
                    document_id=document_id,
                    visibility_tenant_id=tenant_id if document_scope == "local" else None,
                    definition=str(candidate.content.get("definition") or candidate.subject),
                    aliases=_clean_aliases(candidate.aliases, candidate.subject),
                ))
                added += 1
            else:
                exists.definition = str(candidate.content.get("definition") or candidate.subject)
                exists.aliases = _clean_aliases(candidate.aliases, candidate.subject)
                exists.state = "active"
        await self._refresh_glossary_entry(row.id)
        return bool(added)

    async def _withdraw_document_glossary_observations(
        self, document_id: UUID, *, keep_checksum: str | None = None,
    ) -> None:
        observations = (await self._session.execute(select(GlossaryObservation).where(
            GlossaryObservation.source_type == "document",
            GlossaryObservation.source_ref.like(f"{document_id}:%"),
        ))).scalars().all()
        if keep_checksum is not None:
            observations = [row for row in observations if f":{keep_checksum}:" not in row.source_ref]
        await self._withdraw_glossary_observations(
            observations, deactivate_empty=keep_checksum is None,
        )

    async def _withdraw_glossary_observations(
        self, observations: Sequence[GlossaryObservation], *, deactivate_empty: bool = True,
    ) -> None:
        entry_ids = {row.entry_id for row in observations}
        if observations:
            await self._session.execute(delete(GlossaryObservation).where(
                GlossaryObservation.id.in_([row.id for row in observations]),
            ))
        for entry_id in entry_ids:
            await self._refresh_glossary_entry(entry_id, deactivate_empty=deactivate_empty)

    async def _refresh_glossary_entry(self, entry_id: UUID, *, deactivate_empty: bool = True) -> None:
        entry = (await self._session.execute(select(GlossaryEntry).where(
            GlossaryEntry.id == entry_id,
        ))).scalar_one_or_none()
        if entry is None:
            return
        claims = list((await self._session.execute(select(GlossaryObservation).where(
            GlossaryObservation.entry_id == entry_id, GlossaryObservation.state == "active",
        ).order_by(GlossaryObservation.created_at.desc()))).scalars().all())
        entry.support_count = len(claims)
        if not claims:
            if deactivate_empty:
                entry.is_active = False
                entry.status = GlossaryStatus.UNCONFIRMED.value
            return
        definitions = {str(claim.definition or "").strip() for claim in claims}
        entry.is_active = True
        entry.aliases = _clean_aliases(
            [alias for claim in claims for alias in claim.aliases], entry.canonical_term,
        )
        entry.description = str(claims[0].definition or entry.canonical_term)
        entry.status = (
            GlossaryStatus.CONFIRMED.value if len(definitions) == 1
            else GlossaryStatus.UNCONFIRMED.value
        )

    async def _attach_sources(
        self,
        item: MemoryItem,
        document_id: UUID,
        checksum: str,
        section_ids: Sequence[str],
        section_map: dict[str, dict[str, Any]],
    ) -> bool:
        added = False
        for section_id in section_ids:
            exists = (await self._session.execute(select(MemoryItemSource.id).where(
                MemoryItemSource.memory_item_id == item.id,
                MemoryItemSource.document_id == document_id,
                MemoryItemSource.canonical_checksum == checksum,
                MemoryItemSource.section_id == section_id,
            ))).scalar_one_or_none()
            if exists is not None:
                continue
            section = section_map[section_id]
            excerpt = str(section.get("text") or "")
            self._session.add(MemoryItemSource(
                memory_item_id=item.id, document_id=document_id, canonical_checksum=checksum,
                section_id=section_id, start_offset=section.get("start_offset"), end_offset=section.get("end_offset"),
                excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
                label=str(section.get("label") or section_id)[:255],
            ))
            added = True
        return added


async def retire_document_memory(session: AsyncSession, *, document_id: UUID) -> dict[UUID, str]:
    """Retire only this document's evidence and reconsolidate shared items."""
    service = DocumentMemoryService(session)
    item_ids = set((await session.execute(select(MemoryItemSource.memory_item_id).where(
        MemoryItemSource.document_id == document_id,
    ))).scalars().all())
    item_ids.update((await session.execute(select(MemoryClaim.memory_item_id).where(
        MemoryClaim.document_id == document_id, MemoryClaim.state == "active",
    ))).scalars().all())
    await session.execute(update(MemoryClaim).where(
        MemoryClaim.document_id == document_id, MemoryClaim.state == "active",
    ).values(state="stale"))
    await session.execute(delete(MemoryItemSource).where(MemoryItemSource.document_id == document_id))
    await session.execute(delete(MemoryRelation).where(MemoryRelation.document_id == document_id))
    await service._withdraw_document_glossary_observations(document_id)
    await service._retire_entity_sources(document_id)
    for item_id in item_ids:
        await service._consolidate_item(item_id)
    await session.flush()
    rows = (await session.execute(select(MemoryItem.id, MemoryItem.state).where(
        MemoryItem.id.in_(item_ids),
    ))).all() if item_ids else []
    return {item_id: state for item_id, state in rows}


def split_canonical_sections(text: str, *, max_chars: int = 5_000) -> list[dict[str, Any]]:
    """Create bounded addressable sections while preserving paragraph boundaries."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    sections: list[dict[str, Any]] = []
    parts: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text or ""):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        start = match.start() + len(raw) - len(raw.lstrip())
        parts.append((start, start + len(stripped), stripped))

    buffer: list[tuple[int, int, str]] = []
    buffer_len = 0
    def flush() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        start = buffer[0][0]
        end = buffer[-1][1]
        rendered = "\n\n".join(part[2] for part in buffer)
        sections.append(_section(len(sections), rendered, start, end))
        buffer, buffer_len = [], 0

    for start, end, paragraph in parts:
        # Split an exceptionally long paragraph without fabricating its source
        # coordinates. Normal paragraphs stay intact.
        chunks = [(start + index, min(start + index + max_chars, end), paragraph[index:index + max_chars])
                  for index in range(0, len(paragraph), max_chars)]
        for chunk_start, chunk_end, chunk in chunks:
            extra = 2 if buffer else 0
            if buffer and buffer_len + extra + len(chunk) > max_chars:
                flush()
            buffer.append((chunk_start, chunk_end, chunk))
            buffer_len += (2 if buffer_len else 0) + len(chunk)
            if len(chunk) == max_chars:
                flush()
    flush()
    return sections


def _section(index: int, text: str, start: int, end: int) -> dict[str, Any]:
    label = text.splitlines()[0][:120] if text else f"section {index + 1}"
    return {"id": f"section-{index + 1}", "label": label, "text": text, "start_offset": start, "end_offset": end}


def _normalize_subject(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())[:200]


def _normalize_project_key(value: str | None) -> str | None:
    key = str(value or "").strip().lower()
    return key or None


def _clean_aliases(values: Sequence[object], canonical: str) -> list[str]:
    seen = {str(canonical).casefold()}
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())[:255]
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            result.append(cleaned)
    return result


def _content_text(content: dict[str, Any]) -> str:
    # The structured payload is the source of truth.  This text is only a
    # search projection and must never silently cut a procedure mid-JSON.
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _procedure_content(content: dict[str, Any]) -> dict[str, Any] | None:
    """Compatibility helper used by tests and callers of the old helper."""
    try:
        return normalize_memory_content("procedure", content)
    except ValueError:
        return None


def _item_applicability(candidate: DocumentMemoryCandidate, project: Project | None) -> dict[str, Any]:
    # Do not persist extractor-defined keys the Recall contract cannot
    # evaluate.  Unknown restrictions would otherwise be silently ignored.
    raw = dict(candidate.applicability or {})
    result = {
        key: [str(value) for value in raw.get(key) or [] if str(value).strip()]
        for key in ("project_ids", "tenant_ids") if isinstance(raw.get(key), list)
    }
    if project is not None:
        project_ids = [str(item) for item in result.get("project_ids") or [] if str(item).strip()]
        if str(project.id) not in project_ids:
            project_ids.append(str(project.id))
        result["project_ids"] = project_ids
    return result


def _related_entities(values: Sequence[dict[str, str]]) -> list[tuple[str, str, str]]:
    """Accept only bounded, typed graph edges from the extractor contract."""
    result: list[tuple[str, str, str]] = []
    for value in values[:12]:
        if not isinstance(value, dict):
            continue
        target_type = str(value.get("target_type") or "").strip().lower()
        target_id = str(value.get("target_id") or "").strip()
        relation_type = str(value.get("relation_type") or "related_to").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_:-]{0,63}", target_type):
            continue
        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_.:-]{1,255}", target_id):
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_:-]{0,63}", relation_type):
            continue
        edge = (target_type, target_id, relation_type)
        if edge not in result:
            result.append(edge)
    return result


def _logical_section_groups(
    sections: Sequence[dict[str, Any]], *, max_chars: int = 12_000, overlap: int = 1,
) -> list[list[dict[str, Any]]]:
    """Bound extraction payloads while retaining continuity at group boundaries."""
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for section in sections:
        text_size = len(str(section.get("text") or ""))
        if current and current_size + text_size > max_chars:
            groups.append(current)
            current = current[-overlap:] if overlap else []
            current_size = sum(len(str(item.get("text") or "")) for item in current)
        current.append(dict(section))
        current_size += text_size
    if current:
        groups.append(current)
    return groups


def _shortlist_projects(
    document: dict[str, Any], sections: Sequence[dict[str, Any]], projects: Sequence[dict[str, Any]], *, limit: int = 40,
) -> list[dict[str, Any]]:
    """Avoid sending the whole company catalogue to each extraction call."""
    text = _normalize_subject(" ".join([
        str(document.get("title") or ""),
        str(document.get("filename") or ""),
        *(str(section.get("text") or "") for section in sections),
    ]))
    explicit_keys = {_normalize_project_key(value) for value in document.get("project_keys") or []}
    ranked: list[tuple[int, dict[str, Any]]] = []
    for project in projects:
        forms = [project.get("key"), project.get("name"), *(project.get("aliases") or [])]
        score = sum(1 for form in forms if len(_normalize_subject(str(form))) >= 3 and _normalize_subject(str(form)) in text)
        if _normalize_project_key(project.get("key")) in explicit_keys:
            score += 100
        if score:
            ranked.append((score, dict(project)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [project for _, project in ranked[:limit]]
