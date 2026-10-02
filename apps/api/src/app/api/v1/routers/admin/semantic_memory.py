"""Admin inspection endpoints for document-derived semantic memory."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.security import UserCtx
from app.models.rag import RAGDocument
from app.models.document_memory_staging import (
    DocumentMemoryExtractionAttempt, DocumentMemorySnapshot, GlossaryTerm, MemoryCandidateProjectBinding,
    MemoryCandidateScopeProposal, MemoryConflictCase, MemoryConflictMember,
    MemoryExtractionCandidate, MemoryScopeProposal,
)
from app.models.memory_scope import MemoryCandidateScope, MemoryClaimScope, MemoryScope
from app.models.project import Project
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.runtime.memory.index_dispatch import dispatch_memory_index
from app.runtime.memory.shadow_document_study import ShadowDocumentStudyService
from app.models.rag_ingest import RAGStatus, Source
from app.services.semantic_memory_admin_service import (
    SemanticMemoryAdminService,
    SemanticMemoryListRow,
)
from app.services.memory_scope_catalog import list_memory_scopes
from app.services.glossary_service import GlossaryService
from app.services.lifecycle_admin_service import LifecycleAdminService
from app.runtime.memory.content_contracts import content_contract_error
from app.runtime.memory.document_sections import split_canonical_sections
from app.storage.paths import calculate_text_checksum
from app.workers.tasks_shadow_document_memory import study_shadow_document_sections


router = APIRouter(prefix="/memory")


class SemanticMemoryBulkDeactivateRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


class SemanticMemoryBulkDeactivateResponse(BaseModel):
    deactivated: int


class ShadowCandidateEvidenceSection(BaseModel):
    id: str
    label: str
    text: str


class ShadowCandidateEvidenceResponse(BaseModel):
    document_title: str
    sections: list[ShadowCandidateEvidenceSection]


class SemanticMemoryItemResponse(BaseModel):
    id: UUID
    scope: str
    item_type: str
    project_id: UUID | None
    scope_keys: list[str] = Field(default_factory=list)
    subject: str
    content_text: str
    content: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    state: str
    applicability: dict[str, Any] = Field(default_factory=dict)
    visibility: dict[str, Any] = Field(default_factory=dict)
    last_verified_at: datetime
    updated_at: datetime
    source_count: int
    claim_count: int


class SemanticMemorySourceResponse(BaseModel):
    document_id: UUID
    canonical_checksum: str
    section_id: str
    label: str | None
    start_offset: int | None
    end_offset: int | None


class SemanticMemoryClaimResponse(BaseModel):
    id: UUID
    document_id: UUID
    canonical_checksum: str
    scope: str
    item_type: str
    project_id: UUID | None
    scope_keys: list[str] = Field(default_factory=list)
    normalized_subject: str
    confidence: float
    state: str
    evidence_section_ids: list[str]
    content: dict[str, Any] = Field(default_factory=dict)
    applicability: dict[str, Any] = Field(default_factory=dict)
    visibility_tenant_id: UUID | None = None
    updated_at: datetime


class SemanticMemoryDetailResponse(SemanticMemoryItemResponse):
    sources: list[SemanticMemorySourceResponse]
    claims: list[SemanticMemoryClaimResponse]
    relations: list[dict[str, str]]
    evaluations: list[dict[str, Any]]


class SemanticMemoryPageResponse(BaseModel):
    items: list[SemanticMemoryItemResponse]
    total: int
    limit: int
    offset: int


class SemanticMemoryExtractionStatusResponse(BaseModel):
    document_id: UUID
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class SemanticMemoryStagingOverviewResponse(BaseModel):
    snapshots: dict[str, int] = Field(default_factory=dict)
    candidates: dict[str, int] = Field(default_factory=dict)
    project_bindings: dict[str, int] = Field(default_factory=dict)


class ShadowReextractResponse(BaseModel):
    snapshot_id: UUID
    attempt_id: UUID
    attempt_number: int
    status: str


class ShadowCandidateResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    visibility_tenant_id: UUID | None
    document_title: str | None = None
    document_access_scope: str | None = None
    candidate_type: str
    subject: str
    normalized_subject: str
    content: dict[str, Any]
    content_text: str = ""
    content_valid: bool = True
    content_error: str | None = None
    aliases: list[str] = Field(default_factory=list)
    related_entities: list[dict[str, Any]] = Field(default_factory=list)
    glossary_term_ids: list[UUID] = Field(default_factory=list)
    related_project_keys: list[str] = Field(default_factory=list)
    evidence_section_ids: list[str]
    scope_candidate: str | None
    resolution_status: str
    extraction_confidence: float
    project_ids: list[UUID] = Field(default_factory=list)
    scope_ids: list[UUID] = Field(default_factory=list)
    scope_keys: list[str] = Field(default_factory=list)
    mentioned_scope_keys: list[str] = Field(default_factory=list)
    unmatched_scope_names: list[str] = Field(default_factory=list)
    scope_rationale: str | None = None
    conflict_ids: list[UUID] = Field(default_factory=list)
    scope_proposals: list[dict[str, Any]] = Field(default_factory=list)
    related_terms: list[dict[str, Any]] = Field(default_factory=list)
    approval_blockers: list[str] = Field(default_factory=list)


class ShadowCandidateDecisionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str | None = Field(default=None, max_length=2000)
    replace_existing_definition: bool = False


class ShadowCandidateTagsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    scope_ids: list[UUID] = Field(max_length=64)
    company_wide: bool
    glossary_term_ids: list[UUID] = Field(max_length=64)
    reason: str = Field(default="", max_length=2000)


class MemoryTermTagResponse(BaseModel):
    id: UUID
    canonical_term: str
    definition: str
    aliases: list[str]


class ShadowCandidateRejectRequest(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str = Field(min_length=1, max_length=2000)


class MemoryScopeProposalResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    visibility_tenant_id: UUID | None
    scope_type: str
    proposed_key: str
    name: str
    aliases: list[str]
    term_candidate_id: UUID | None
    glossary_term_id: UUID | None
    term_name: str
    memory_scope_id: UUID | None
    evidence_section_ids: list[str]
    rationale: str
    status: str
    rejection_reason: str | None
    dependent_candidate_ids: list[UUID] = Field(default_factory=list)
    approval_blockers: list[str] = Field(default_factory=list)


class MemoryScopeResponse(BaseModel):
    id: UUID
    scope_type: str
    key: str
    name: str
    aliases: list[str]
    is_all: bool
    project_id: UUID | None = None
    lifecycle_status: str = "active"
    retention_days: int = 14


class MemoryScopeWriteRequest(BaseModel):
    scope_type: str = Field(pattern="^(product|project|team)$")
    key: str = Field(min_length=3, max_length=180, pattern="^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    is_all: bool = False


def _memory_scope_response(row: MemoryScope) -> MemoryScopeResponse:
    return MemoryScopeResponse(id=row.id, scope_type=row.scope_type, key=row.key, name=row.name,
                               aliases=list(row.aliases or []), is_all=row.is_all, project_id=row.project_id,
                               lifecycle_status=row.lifecycle_status, retention_days=row.retention_days)


async def _candidate_scope_proposals(db: AsyncSession, candidate_id: UUID) -> list[dict[str, Any]]:
    rows = (await db.execute(select(
        MemoryCandidateScopeProposal.role,
        MemoryCandidateScopeProposal.status,
        MemoryScopeProposal.id,
        MemoryScopeProposal.name,
        MemoryScopeProposal.scope_type,
        MemoryScopeProposal.status,
        MemoryScopeProposal.rejection_reason,
        MemoryScopeProposal.term_candidate_id,
        MemoryScopeProposal.glossary_term_id,
    ).join(
        MemoryScopeProposal,
        MemoryScopeProposal.id == MemoryCandidateScopeProposal.scope_proposal_id,
    ).where(MemoryCandidateScopeProposal.candidate_id == candidate_id, MemoryCandidateScopeProposal.status != "superseded"))).all()
    result = []
    for role, binding_status, proposal_id, name, scope_type, status, rejection, term_candidate_id, glossary_term_id in rows:
        term_name = None
        if term_candidate_id:
            term_name = await db.scalar(select(MemoryExtractionCandidate.subject).where(
                MemoryExtractionCandidate.id == term_candidate_id,
            ))
        elif glossary_term_id:
            term_name = await db.scalar(select(GlossaryTerm.canonical_term).where(
                GlossaryTerm.id == glossary_term_id,
            ))
        result.append({"id": str(proposal_id), "name": name, "scope_type": scope_type,
                       "status": status, "role": role, "binding_status": binding_status,
                       "term_name": term_name, "rejection_reason": rejection})
    return result


async def _candidate_related_terms(db: AsyncSession, candidate_id: UUID) -> list[dict[str, Any]]:
    proposals = await db.scalars(select(MemoryScopeProposal).join(
        MemoryCandidateScopeProposal,
        MemoryCandidateScopeProposal.scope_proposal_id == MemoryScopeProposal.id,
    ).where(MemoryCandidateScopeProposal.candidate_id == candidate_id, MemoryCandidateScopeProposal.status != "superseded"))
    result = []
    candidate = await db.get(MemoryExtractionCandidate, candidate_id)
    for entity in candidate.related_entities or [] if candidate else []:
        if entity.get("type") == "glossary_term":
            result.append({"id": entity.get("id"), "term": entity.get("name", ""), "scope": "", "status": "confirmed"})
    for proposal in proposals:
        term_name = None
        if proposal.term_candidate_id:
            term_name = await db.scalar(select(MemoryExtractionCandidate.subject).where(
                MemoryExtractionCandidate.id == proposal.term_candidate_id,
            ))
        elif proposal.glossary_term_id:
            term_name = await db.scalar(select(GlossaryTerm.canonical_term).where(
                GlossaryTerm.id == proposal.glossary_term_id,
            ))
        if term_name:
            result.append({"term": term_name, "scope": proposal.name, "status": proposal.status})
    return result


async def _candidate_approval_blockers(
    db: AsyncSession, candidate_id: UUID, candidate_type: str, scope_candidate: str | None,
    unresolved_scope_references: list[dict[str, Any]] = (),
    glossary_term_ids: list[UUID] = (),
) -> list[str]:
    if candidate_type == "term":
        return []
    rows = (await db.execute(select(
        MemoryScopeProposal.name,
        MemoryScopeProposal.status,
        MemoryScopeProposal.rejection_reason,
        MemoryCandidateScopeProposal.status,
    ).join(
        MemoryCandidateScopeProposal,
        MemoryCandidateScopeProposal.scope_proposal_id == MemoryScopeProposal.id,
    ).where(
        MemoryCandidateScopeProposal.candidate_id == candidate_id,
        MemoryCandidateScopeProposal.role == "applies_to",
        MemoryCandidateScopeProposal.status != "superseded",
        (MemoryCandidateScopeProposal.status == "rejected") | (MemoryScopeProposal.status != "approved"),
    ))).all()
    blockers = [
        f"Скоуп «{name}» отклонён: {reason or 'причина не указана'}"
        if binding_status == "rejected" or status == "rejected"
        else f"Ожидает утверждения скоупа «{name}»"
        for name, status, reason, binding_status in rows
    ]
    blockers.extend(f"Не разрешена применимость «{ref.get('name') or ref.get('key', '')}»: {ref.get('reason', 'unknown')}"
                    for ref in unresolved_scope_references)
    known_scope_id = await db.scalar(select(MemoryCandidateScope.id).join(
        MemoryScope, MemoryScope.id == MemoryCandidateScope.scope_id,
    ).where(
        MemoryCandidateScope.candidate_id == candidate_id,
        MemoryCandidateScope.role == "applies_to",
        MemoryCandidateScope.status != "rejected",
        MemoryScope.lifecycle_status == "active",
    ).limit(1))
    linked_term = await db.scalar(GlossaryService.published_terms_query().where(
        GlossaryTerm.id.in_(glossary_term_ids),
    ).limit(1)) if glossary_term_ids else None
    if known_scope_id is None and linked_term is None:
        blockers.append("Выберите хотя бы один проект, команду, продукт или термин.")
    if scope_candidate == "project":
        project_ids = list((await db.scalars(select(MemoryCandidateProjectBinding.project_id).where(
            MemoryCandidateProjectBinding.candidate_id == candidate_id,
            MemoryCandidateProjectBinding.role == "applies_to",
            MemoryCandidateProjectBinding.status != "rejected",
        ))).all())
        if len(set(project_ids)) != 1:
            blockers.append("Для проектной памяти должен быть однозначно определён проект.")
    return blockers


async def _scope_proposal_response(db: AsyncSession, proposal: MemoryScopeProposal) -> MemoryScopeProposalResponse:
    if proposal.term_candidate_id:
        term_name = await db.scalar(select(MemoryExtractionCandidate.subject).where(
            MemoryExtractionCandidate.id == proposal.term_candidate_id,
        )) or ""
        term_ready = await db.scalar(select(GlossaryTerm.id).join(
            MemoryExtractionCandidate,
            MemoryExtractionCandidate.id == GlossaryTerm.approved_candidate_id,
        ).where(
            MemoryExtractionCandidate.id == proposal.term_candidate_id,
            MemoryExtractionCandidate.resolution_status == "resolved",
            GlossaryTerm.is_active.is_(True),
        )) is not None
    else:
        term_name = await db.scalar(select(GlossaryTerm.canonical_term).where(
            GlossaryTerm.id == proposal.glossary_term_id,
        )) or ""
        term_ready = bool(await db.scalar(select(GlossaryTerm.id).where(
            GlossaryTerm.id == proposal.glossary_term_id, GlossaryTerm.is_active.is_(True),
        )))
    dependent = list((await db.scalars(select(MemoryCandidateScopeProposal.candidate_id).where(
        MemoryCandidateScopeProposal.scope_proposal_id == proposal.id,
        MemoryCandidateScopeProposal.role == "applies_to",
        MemoryCandidateScopeProposal.status.in_(("suggested", "confirmed")),
    ))).all())
    blockers = []
    if proposal.status == "awaiting_term" or not term_ready:
        blockers.append(f"Ожидает утверждения термина «{term_name}»")
    if proposal.status == "rejected":
        blockers.append(f"Скоуп отклонён: {proposal.rejection_reason or 'причина не указана'}")
    return MemoryScopeProposalResponse(
        id=proposal.id, snapshot_id=proposal.snapshot_id,
        visibility_tenant_id=proposal.visibility_tenant_id,
        scope_type=proposal.scope_type, proposed_key=proposal.proposed_key,
        name=proposal.name, aliases=list(proposal.aliases or []),
        term_candidate_id=proposal.term_candidate_id, glossary_term_id=proposal.glossary_term_id,
        term_name=term_name, memory_scope_id=proposal.memory_scope_id,
        evidence_section_ids=list(proposal.evidence_section_ids or []),
        rationale=proposal.rationale, status=proposal.status,
        rejection_reason=proposal.rejection_reason,
        dependent_candidate_ids=dependent, approval_blockers=blockers,
    )


@router.get("/scopes", response_model=list[MemoryScopeResponse])
async def get_memory_scopes(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return [_memory_scope_response(row) for row in await list_memory_scopes(db, include_deprecated=True)]


@router.post("/scopes", response_model=MemoryScopeResponse, status_code=201)
async def create_memory_scope(body: MemoryScopeWriteRequest, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    if not body.key.startswith(f"{body.scope_type}.") or body.is_all != (body.key == f"{body.scope_type}.all"):
        raise HTTPException(status_code=422, detail="scope_key_type_mismatch")
    row = MemoryScope(scope_type=body.scope_type, key=body.key, name=body.name.strip(),
                      aliases=[alias.strip() for alias in body.aliases if alias.strip()], is_all=body.is_all)
    if body.scope_type == "project" and not body.is_all:
        row.project_id = (await db.execute(select(Project.id).where(
            Project.key == body.key.removeprefix("project."),
        ))).scalar_one_or_none()
    db.add(row)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="memory_scope_identity_conflict") from exc
    return _memory_scope_response(row)


@router.patch("/scopes/{scope_id}", response_model=MemoryScopeResponse)
async def update_memory_scope(scope_id: UUID, body: MemoryScopeWriteRequest,
                              db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    row = await db.get(MemoryScope, scope_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    if not body.key.startswith(f"{body.scope_type}.") or body.is_all != (body.key == f"{body.scope_type}.all"):
        raise HTTPException(status_code=422, detail="scope_key_type_mismatch")
    if body.scope_type != row.scope_type or body.key != row.key or body.is_all != row.is_all:
        raise HTTPException(status_code=409, detail="scope_identity_is_immutable")
    row.scope_type = body.scope_type
    row.key = body.key
    row.name = body.name.strip()
    row.aliases = [alias.strip() for alias in body.aliases if alias.strip()]
    row.is_all = body.is_all
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="memory_scope_identity_conflict") from exc
    return _memory_scope_response(row)


def _item_response(row: SemanticMemoryListRow) -> SemanticMemoryItemResponse:
    item = row.item
    return SemanticMemoryItemResponse(
        id=item.id, scope="scoped" if item.scope_signature != "legacy" else item.scope,
        item_type=item.item_type, project_id=item.project_id,
        scope_keys=list(row.scope_keys),
        subject=item.subject, content_text=item.content_text, content=dict(item.content or {}), confidence=item.confidence,
        state=item.state, applicability=dict(item.applicability or {}), visibility=dict(item.visibility or {}),
        last_verified_at=item.last_verified_at, updated_at=item.updated_at,
        source_count=row.source_count, claim_count=row.claim_count,
    )


@router.get("", response_model=SemanticMemoryPageResponse)
async def list_semantic_memory(
    scope: str | None = Query(default=None, pattern="^(company|project|scoped)$"),
    state: str | None = Query(default=None, pattern="^(active|stale|uncertain)$"),
    item_type: str | None = Query(default=None, pattern="^(description|relationship|rule|constraint|procedure|decision)$"),
    project_id: UUID | None = None,
    scope_type: str | None = Query(default=None, max_length=80),
    scope_id: UUID | None = None,
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    rows = await SemanticMemoryAdminService(db).list_items(
        scope=scope, state=state, item_type=item_type, project_id=project_id,
        scope_type=scope_type, scope_id=scope_id,
        query=query, limit=limit, offset=offset,
    )
    return SemanticMemoryPageResponse(
        items=[_item_response(row) for row in rows.rows], total=rows.total,
        limit=limit, offset=offset,
    )


@router.post("/bulk-deactivate", response_model=SemanticMemoryBulkDeactivateResponse)
async def bulk_deactivate_semantic_memory(
    payload: SemanticMemoryBulkDeactivateRequest,
    db: AsyncSession = Depends(db_session),
    admin_user: UserCtx = Depends(require_admin),
):
    service = LifecycleAdminService(db)
    unique_ids = list(dict.fromkeys(payload.ids))
    for item_id in unique_ids:
        try:
            await service.soft_delete(
                "memory_item", item_id,
                actor_id=UUID(str(admin_user.id)) if admin_user.id else None,
                reason="Deactivated by administrator",
                retention_days=None,
                cascade=False,
            )
        except ValueError as exc:
            await db.rollback()
            if str(exc) == "not_found":
                raise HTTPException(status_code=404, detail="One or more memory items were not found") from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return SemanticMemoryBulkDeactivateResponse(deactivated=len(unique_ids))


@router.get("/documents/{document_id}/status", response_model=SemanticMemoryExtractionStatusResponse)
async def get_document_memory_extraction_status(
    document_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    snapshot = (await db.execute(select(DocumentMemorySnapshot).where(
        DocumentMemorySnapshot.document_id == document_id,
    ).order_by(DocumentMemorySnapshot.updated_at.desc()).limit(1))).scalar_one_or_none()
    status = (await db.execute(select(RAGStatus).where(
        RAGStatus.doc_id == document_id, RAGStatus.node_type == "memory", RAGStatus.node_key == "extract",
    ))).scalar_one_or_none()
    return SemanticMemoryExtractionStatusResponse(
        document_id=document_id,
        status=snapshot.status if snapshot is not None else (status.status if status is not None else "not_queued"),
        metrics=dict(snapshot.metrics or {}) if snapshot is not None else (dict(status.metrics_json or {}) if status is not None else {}),
    )


@router.get("/staging/overview", response_model=SemanticMemoryStagingOverviewResponse)
async def get_semantic_memory_staging_overview(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """P0 diagnostics for the new claim/applicability model."""
    overview = await SemanticMemoryAdminService(db).staging_overview()
    return SemanticMemoryStagingOverviewResponse(
        snapshots=overview.snapshots,
        candidates=overview.candidates,
        project_bindings=overview.project_bindings,
    )


@router.get("/staging/candidates", response_model=list[ShadowCandidateResponse])
async def list_shadow_candidates(
    status: str | None = Query(default=None, pattern="^(pending|needs_review|conflict|resolved|rejected)$"),
    candidate_type: str | None = Query(default=None, pattern="^(term|description|relationship|rule|constraint|procedure|decision)$"),
    tenant_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    stmt = select(MemoryExtractionCandidate).order_by(MemoryExtractionCandidate.updated_at.desc(), MemoryExtractionCandidate.id).limit(limit).offset(offset)
    if status == "pending":
        stmt = stmt.where(MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review", "conflict")))
    elif status:
        stmt = stmt.where(MemoryExtractionCandidate.resolution_status == status)
    if tenant_id:
        stmt = stmt.where(MemoryExtractionCandidate.visibility_tenant_id == tenant_id)
    if candidate_type:
        stmt = stmt.where(MemoryExtractionCandidate.candidate_type == candidate_type)
    rows = list((await db.execute(stmt)).scalars().all())
    document_rows = (await db.execute(select(
        DocumentMemorySnapshot.id, RAGDocument.title, RAGDocument.scope,
    ).join(RAGDocument, RAGDocument.id == DocumentMemorySnapshot.document_id).where(
        DocumentMemorySnapshot.id.in_({row.snapshot_id for row in rows}),
    ))).all() if rows else []
    documents = {snapshot_id: (title, scope) for snapshot_id, title, scope in document_rows}
    result: list[ShadowCandidateResponse] = []
    for row in rows:
        result.append(await _shadow_candidate_response(db, row, documents.get(row.snapshot_id, (None, None))))
    return result


@router.get("/staging/term-catalog", response_model=list[MemoryTermTagResponse])
async def list_memory_term_tags(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return [MemoryTermTagResponse(id=term["id"], canonical_term=term["term"], definition=term["definition"],
                                  aliases=term["aliases"])
            for term in await GlossaryService(db).list_confirmed_terms()]


async def _shadow_candidate_response(
    db: AsyncSession, row: MemoryExtractionCandidate, document: tuple[str | None, str | None] = (None, None),
) -> ShadowCandidateResponse:
    validation_error = content_contract_error(row.candidate_type, dict(row.content or {}))
    project_ids = list((await db.execute(select(MemoryCandidateProjectBinding.project_id).where(
        MemoryCandidateProjectBinding.candidate_id == row.id,
    ))).scalars().all())
    scope_rows = (await db.execute(select(MemoryCandidateScope.scope_id, MemoryScope.key, MemoryCandidateScope.role).join(
        MemoryScope, MemoryScope.id == MemoryCandidateScope.scope_id,
    ).where(
        MemoryCandidateScope.candidate_id == row.id,
        MemoryCandidateScope.status != "rejected",
        MemoryScope.lifecycle_status == "active",
    ))).all()
    conflict_ids = list((await db.execute(select(MemoryConflictMember.conflict_id).join(MemoryConflictCase, MemoryConflictCase.id == MemoryConflictMember.conflict_id).where(MemoryConflictMember.candidate_id == row.id, MemoryConflictCase.status == "open", MemoryConflictCase.kind.in_(("contradiction", "insufficient_evidence"))))).scalars().all())
    return ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
        document_title=document[0],
        document_access_scope=document[1],
        candidate_type=row.candidate_type, subject=row.subject, normalized_subject=row.normalized_subject,
        content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
        glossary_term_ids=[UUID(entity["id"]) for entity in row.related_entities or [] if entity.get("type") == "glossary_term" and entity.get("id")],
        content_text=row.content_text, aliases=list(row.aliases or []), related_entities=list(row.related_entities or []), related_project_keys=list(row.related_project_keys or []),
        content_valid=validation_error is None, content_error=validation_error,
        scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence,
        project_ids=project_ids,
        scope_ids=[scope_id for scope_id, _, role in scope_rows if role == "applies_to"],
        scope_keys=[key for _, key, role in scope_rows if role == "applies_to"],
        mentioned_scope_keys=[key for _, key, role in scope_rows if role == "mentions"],
        unmatched_scope_names=list(row.unmatched_scope_names or []),
        scope_rationale=row.resolution_rationale,
        conflict_ids=conflict_ids,
        scope_proposals=await _candidate_scope_proposals(db, row.id),
        related_terms=await _candidate_related_terms(db, row.id),
        approval_blockers=await _candidate_approval_blockers(
            db, row.id, row.candidate_type, row.scope_candidate, row.unresolved_scope_references or [],
            [UUID(entity["id"]) for entity in row.related_entities or []
             if entity.get("type") == "glossary_term" and entity.get("id")],
        ))


@router.patch("/staging/candidates/{candidate_id}/tags", response_model=ShadowCandidateResponse)
async def update_shadow_candidate_tags(
    candidate_id: UUID, request: ShadowCandidateTagsRequest,
    db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin),
):
    try:
        row = await ShadowMemoryPublicationService(db).update_review_tags(
            candidate_id=candidate_id, actor_id=UUID(user.id), scope_ids=request.scope_ids,
            company_wide=request.company_wide, glossary_term_ids=request.glossary_term_ids, reason=request.reason,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    snapshot = await db.get(DocumentMemorySnapshot, row.snapshot_id)
    source = await db.get(RAGDocument, snapshot.document_id) if snapshot else None
    return await _shadow_candidate_response(db, row, (source.title, source.scope) if source else (None, None))


@router.get("/staging/retryable-snapshots")
async def list_retryable_shadow_snapshots(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    rejected_candidate = select(MemoryExtractionCandidate.id).where(
        MemoryExtractionCandidate.attempt_id == DocumentMemorySnapshot.active_attempt_id,
        MemoryExtractionCandidate.resolution_status == "rejected",
    ).exists()
    rejected_scope = select(MemoryScopeProposal.id).where(
        MemoryScopeProposal.attempt_id == DocumentMemorySnapshot.active_attempt_id,
        MemoryScopeProposal.status == "rejected",
    ).exists()
    rows = (await db.execute(select(DocumentMemorySnapshot, RAGDocument.title, DocumentMemoryExtractionAttempt.attempt_number).join(
        RAGDocument, RAGDocument.id == DocumentMemorySnapshot.document_id,
    ).outerjoin(
        DocumentMemoryExtractionAttempt, DocumentMemoryExtractionAttempt.id == DocumentMemorySnapshot.active_attempt_id,
    ).where(
        DocumentMemorySnapshot.status.in_(("awaiting_review", "approved", "rejected", "failed")),
        RAGDocument.status != "archived",
        or_(rejected_candidate, rejected_scope, DocumentMemorySnapshot.status == "failed"),
    ).order_by(DocumentMemorySnapshot.updated_at.desc()).limit(100))).all()
    return [{"snapshot_id": str(row.id), "document_title": title,
             "status": row.status, "attempt_number": number} for row, title, number in rows]


@router.post("/staging/snapshots/{snapshot_id}/reextract", response_model=ShadowReextractResponse, status_code=202)
async def reextract_shadow_snapshot(snapshot_id: UUID, db: AsyncSession = Depends(db_session),
                                    _: UserCtx = Depends(require_admin)):
    snapshot = await db.scalar(select(DocumentMemorySnapshot).where(
        DocumentMemorySnapshot.id == snapshot_id,
    ).with_for_update().execution_options(populate_existing=True))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    document = await db.get(RAGDocument, snapshot.document_id)
    if document is None or document.status == "archived":
        raise HTTPException(status_code=409, detail="document_source_unavailable")
    old_attempt = await db.get(DocumentMemoryExtractionAttempt, snapshot.active_attempt_id) if snapshot.active_attempt_id else None
    rejected = await db.scalar(select(MemoryExtractionCandidate.id).where(
        MemoryExtractionCandidate.snapshot_id == snapshot.id,
        MemoryExtractionCandidate.attempt_id == snapshot.active_attempt_id,
        MemoryExtractionCandidate.resolution_status == "rejected",
    ).limit(1))
    rejected_scope = await db.scalar(select(MemoryScopeProposal.id).where(
        MemoryScopeProposal.snapshot_id == snapshot.id,
        MemoryScopeProposal.attempt_id == snapshot.active_attempt_id,
        MemoryScopeProposal.status == "rejected",
    ).limit(1))
    if rejected is None and rejected_scope is None and snapshot.status != "failed":
        raise HTTPException(status_code=409, detail="rejection_required_before_reextract")
    if snapshot.status not in {"awaiting_review", "approved", "rejected", "failed"}:
        raise HTTPException(status_code=409, detail="snapshot_not_retryable")
    feedback = await ShadowDocumentStudyService(db).reextraction_feedback(snapshot.id, snapshot.active_attempt_id)
    if not feedback and old_attempt is not None:
        feedback = list(old_attempt.feedback or [])[:40]
    if old_attempt is not None:
        old_attempt.status = "superseded"
        await db.execute(update(MemoryExtractionCandidate).where(
            MemoryExtractionCandidate.attempt_id == old_attempt.id,
            MemoryExtractionCandidate.resolution_status.in_(("extracted", "needs_review", "conflict")),
        ).values(resolution_status="stale"))
        await db.execute(update(MemoryScopeProposal).where(
            MemoryScopeProposal.attempt_id == old_attempt.id,
            MemoryScopeProposal.status.in_(("awaiting_term", "needs_review")),
        ).values(status="superseded"))
        await db.execute(update(MemoryCandidateScopeProposal).where(
            MemoryCandidateScopeProposal.candidate_id.in_(select(MemoryExtractionCandidate.id).where(
                MemoryExtractionCandidate.attempt_id == old_attempt.id,
                MemoryExtractionCandidate.resolution_status == "stale")),
            MemoryCandidateScopeProposal.status.in_(("suggested", "confirmed")),
        ).values(status="superseded"))
    max_number = await db.scalar(select(func.max(DocumentMemoryExtractionAttempt.attempt_number)).where(
        DocumentMemoryExtractionAttempt.snapshot_id == snapshot.id,
    )) or 0
    attempt = DocumentMemoryExtractionAttempt(snapshot_id=snapshot.id, attempt_number=int(max_number) + 1,
                                               status="queued", feedback=feedback)
    db.add(attempt)
    await db.flush()
    snapshot.active_attempt_id = attempt.id
    snapshot.status = "studying"
    snapshot.metrics = {**dict(snapshot.metrics or {}), "next_section": 0, "reextract_attempt": int(max_number) + 1}
    source_tenant_id = await db.scalar(select(Source.tenant_id).where(Source.source_id == snapshot.document_id))
    if source_tenant_id is None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="document_source_unavailable")
    await db.commit()
    try:
        study_shadow_document_sections.delay(str(snapshot.id), str(source_tenant_id), str(attempt.id), 0)
    except Exception as exc:
        logging.getLogger(__name__).warning("Memory attempt dispatch deferred to reconciliation: %s", type(exc).__name__)
    return ShadowReextractResponse(snapshot_id=snapshot.id, attempt_id=attempt.id,
                                   attempt_number=attempt.attempt_number, status=attempt.status)


@router.get("/staging/scope-proposals", response_model=list[MemoryScopeProposalResponse])
async def list_shadow_scope_proposals(
    status: str | None = Query(default=None, pattern="^(pending|needs_review|awaiting_term|approved|rejected)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin),
):
    stmt = select(MemoryScopeProposal).order_by(
        MemoryScopeProposal.created_at, MemoryScopeProposal.id,
    ).limit(limit).offset(offset)
    if status == "pending":
        stmt = stmt.where(MemoryScopeProposal.status.in_(("awaiting_term", "needs_review")))
    elif status:
        stmt = stmt.where(MemoryScopeProposal.status == status)
    rows = (await db.scalars(stmt)).all()
    return [await _scope_proposal_response(db, row) for row in rows]


@router.post("/staging/scope-proposals/{proposal_id}/approve", response_model=MemoryScopeProposalResponse)
async def approve_shadow_scope_proposal(
    proposal_id: UUID, request: ShadowCandidateDecisionRequest,
    db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin),
):
    try:
        row = await ShadowMemoryPublicationService(db).approve_scope_proposal(
            proposal_id=proposal_id, actor_id=UUID(user.id), reason=request.reason,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="memory_scope_identity_conflict") from exc
    return await _scope_proposal_response(db, row)


@router.post("/staging/scope-proposals/{proposal_id}/reject", response_model=MemoryScopeProposalResponse)
async def reject_shadow_scope_proposal(
    proposal_id: UUID, request: ShadowCandidateRejectRequest,
    db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin),
):
    try:
        row = await ShadowMemoryPublicationService(db).reject_scope_proposal(
            proposal_id=proposal_id, actor_id=UUID(user.id), reason=request.reason,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404 if str(exc) == "Scope proposal not found" else 409, detail=str(exc)) from exc
    return await _scope_proposal_response(db, row)


@router.get("/staging/candidates/{candidate_id}/evidence", response_model=ShadowCandidateEvidenceResponse)
async def get_shadow_candidate_evidence(
    candidate_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    candidate = await db.get(MemoryExtractionCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    snapshot = await db.get(DocumentMemorySnapshot, candidate.snapshot_id)
    document = await db.get(RAGDocument, snapshot.document_id) if snapshot else None
    if snapshot is None or document is None or not document.s3_key_processed:
        raise HTTPException(status_code=404, detail="Source document is unavailable")
    try:
        raw = await s3_manager.get_object(get_settings().S3_BUCKET_RAG, document.s3_key_processed)
        canonical = json.loads(raw.decode("utf-8"))
        text = str(canonical.get("text") or "")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Source document could not be loaded") from exc
    if calculate_text_checksum(text) != snapshot.canonical_checksum:
        raise HTTPException(status_code=409, detail="Source document revision has changed")
    wanted = set((candidate.evidence_section_ids or [])[:8])
    sections = [ShadowCandidateEvidenceSection(id=section["id"], label=section["label"], text=section["text"])
                for section in split_canonical_sections(text) if section["id"] in wanted]
    return ShadowCandidateEvidenceResponse(document_title=document.title or document.filename, sections=sections)


@router.post("/staging/candidates/{candidate_id}/approve", response_model=ShadowCandidateResponse)
async def approve_shadow_candidate(candidate_id: UUID, request: ShadowCandidateDecisionRequest, db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin)):
    publisher = ShadowMemoryPublicationService(db)
    try:
        row = await publisher.approve(candidate_id=candidate_id, actor_id=UUID(user.id), reason=request.reason,
            replace_existing_definition=request.replace_existing_definition)
        await db.commit()
    except ValueError as exc:
        await db.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback(); raise HTTPException(status_code=409, detail="memory_publication_conflict") from exc
    await dispatch_memory_index(publisher.published_item_ids)
    return ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
        candidate_type=row.candidate_type, subject=row.subject, normalized_subject=row.normalized_subject,
        content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
        content_text=row.content_text, aliases=list(row.aliases or []), related_entities=list(row.related_entities or []), related_project_keys=list(row.related_project_keys or []),
        scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence,
        project_ids=[], scope_ids=[], scope_keys=[], mentioned_scope_keys=[], unmatched_scope_names=[], conflict_ids=[])


@router.post("/staging/candidates/{candidate_id}/reject", response_model=ShadowCandidateResponse)
async def reject_shadow_candidate(candidate_id: UUID, request: ShadowCandidateRejectRequest, db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin)):
    try:
        row = await ShadowMemoryPublicationService(db).reject(candidate_id=candidate_id, actor_id=UUID(user.id), reason=request.reason)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        status_code = 404 if str(exc) == "Memory candidate not found" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
        candidate_type=row.candidate_type, subject=row.subject, normalized_subject=row.normalized_subject,
        content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
        content_text=row.content_text, aliases=list(row.aliases or []), related_entities=list(row.related_entities or []), related_project_keys=list(row.related_project_keys or []),
        scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence,
        project_ids=[], scope_ids=[], scope_keys=[], mentioned_scope_keys=[], unmatched_scope_names=[], conflict_ids=[])


@router.get("/{item_id}", response_model=SemanticMemoryDetailResponse)
async def get_semantic_memory_item(
    item_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    detail = await SemanticMemoryAdminService(db).get_item(item_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Semantic memory item not found")
    base = _item_response(SemanticMemoryListRow(
        item=detail.item, source_count=len(detail.sources), claim_count=len(detail.claims),
    )).model_dump()
    scope_rows = (await db.execute(select(MemoryClaimScope.claim_id, MemoryScope.key).join(
        MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id,
    ).where(MemoryClaimScope.claim_id.in_([claim.id for claim in detail.claims])))).all() if detail.claims else []
    claim_scope_keys: dict[UUID, list[str]] = {}
    for claim_id, key in scope_rows:
        claim_scope_keys.setdefault(claim_id, []).append(key)
    base["scope_keys"] = sorted({key for keys in claim_scope_keys.values() for key in keys})
    return SemanticMemoryDetailResponse(
        **base,
        sources=[SemanticMemorySourceResponse(
            document_id=item.document_id, canonical_checksum=item.canonical_checksum,
            section_id=item.section_id, label=item.label,
            start_offset=item.start_offset, end_offset=item.end_offset,
        ) for item in detail.sources],
        claims=[SemanticMemoryClaimResponse(
            id=item.id, document_id=item.document_id, canonical_checksum=item.canonical_checksum,
            scope="scoped" if item.scope_signature != "legacy" else item.scope,
            item_type=item.item_type, project_id=item.project_id,
            scope_keys=claim_scope_keys.get(item.id, []),
            normalized_subject=item.normalized_subject, confidence=item.confidence,
            state=item.state, evidence_section_ids=list(item.evidence_section_ids or []),
            content=dict(item.content or {}), applicability=dict(item.applicability or {}),
            visibility_tenant_id=item.visibility_tenant_id, updated_at=item.updated_at,
        ) for item in detail.claims],
        relations=[{
            "relation_type": item.relation_type, "target_type": item.target_type, "target_id": item.target_id,
        } for item in detail.relations],
        evaluations=[{
            "tool_call_id": item.tool_call_id, "outcome": item.outcome, "reason": item.reason,
            "evidence_refs": list(item.evidence_refs or []), "created_at": item.created_at,
        } for item in detail.evaluations],
    )


@router.post("/documents/{document_id}/reextract", status_code=202)
async def reextract_document_memory(
    document_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Queue a shadow study; candidates remain outside runtime memory."""
    document = await db.get(RAGDocument, document_id)
    source = (await db.execute(select(Source).where(Source.source_id == document_id))).scalar_one_or_none()
    if document is None or source is None:
        raise HTTPException(status_code=404, detail="Document source not found")
    if document.status == "archived" or not document.s3_key_processed:
        raise HTTPException(status_code=409, detail="Document is not eligible for shadow study")
    tenant_id = source.tenant_id or document.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=409, detail="Document has no tenant execution context")
    await db.commit()
    from app.workers.tasks_shadow_document_memory import shadow_study_rag_document
    shadow_study_rag_document.delay({"source_id": str(document.id)}, str(tenant_id))
    return {"document_id": str(document_id), "status": "queued"}
