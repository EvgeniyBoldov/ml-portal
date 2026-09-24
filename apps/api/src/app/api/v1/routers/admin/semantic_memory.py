"""Admin inspection endpoints for document-derived semantic memory."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.rag import RAGDocument
from app.models.document_memory_staging import DocumentMemorySnapshot, MemoryCandidateProjectBinding, MemoryConflictCase, MemoryConflictMember, MemoryExtractionCandidate
from app.models.memory_scope import MemoryCandidateScope, MemoryClaimScope, MemoryScope
from app.models.project import Project
from app.runtime.memory.shadow_memory_publication import ShadowMemoryPublicationService
from app.models.rag_ingest import RAGStatus, Source
from app.services.semantic_memory_admin_service import (
    SemanticMemoryAdminService,
    SemanticMemoryListRow,
)
from app.services.memory_scope_catalog import list_memory_scopes


router = APIRouter(prefix="/memory")


class SemanticMemoryItemResponse(BaseModel):
    id: UUID
    scope: str
    item_type: str
    project_id: UUID | None
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
    glossary_meanings: dict[str, int] = Field(default_factory=dict)
    conflicting_glossary_terms: int = 0


class ShadowCandidateResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    visibility_tenant_id: UUID | None
    candidate_type: str
    subject: str
    content: dict[str, Any]
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


class ShadowCandidateDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    content: dict[str, Any] | None = None
    scope: str | None = Field(default=None, pattern="^(global|project|scoped)$")
    project_id: UUID | None = None
    scope_ids: list[UUID] = Field(default_factory=list)
    promote_to_company: bool = False


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
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    rows = await SemanticMemoryAdminService(db).list_items(
        scope=scope, state=state, item_type=item_type, project_id=project_id,
        query=query, limit=limit, offset=offset,
    )
    return SemanticMemoryPageResponse(
        items=[_item_response(row) for row in rows.rows], total=rows.total,
        limit=limit, offset=offset,
    )


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
        glossary_meanings=overview.glossary_meanings,
        conflicting_glossary_terms=overview.conflicting_glossary_terms,
    )


@router.get("/staging/candidates", response_model=list[ShadowCandidateResponse])
async def list_shadow_candidates(
    status: str | None = Query(default=None, pattern="^(needs_review|conflict|resolved|rejected)$"),
    tenant_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    stmt = select(MemoryExtractionCandidate).order_by(MemoryExtractionCandidate.updated_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(MemoryExtractionCandidate.resolution_status == status)
    if tenant_id:
        stmt = stmt.where(MemoryExtractionCandidate.visibility_tenant_id == tenant_id)
    rows = list((await db.execute(stmt)).scalars().all())
    result: list[ShadowCandidateResponse] = []
    for row in rows:
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
        conflict_ids = list((await db.execute(select(MemoryConflictMember.conflict_id).join(MemoryConflictCase, MemoryConflictCase.id == MemoryConflictMember.conflict_id).where(MemoryConflictMember.candidate_id == row.id, MemoryConflictCase.status == "open"))).scalars().all())
        result.append(ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
            candidate_type=row.candidate_type, subject=row.subject, content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
            scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence,
            project_ids=project_ids,
            scope_ids=[scope_id for scope_id, _, role in scope_rows if role == "applies_to"],
            scope_keys=[key for _, key, role in scope_rows if role == "applies_to"],
            mentioned_scope_keys=[key for _, key, role in scope_rows if role == "mentions"],
            unmatched_scope_names=list(row.unmatched_scope_names or []),
            scope_rationale=row.resolution_rationale,
            conflict_ids=conflict_ids))
    return result


@router.post("/staging/candidates/{candidate_id}/approve", response_model=ShadowCandidateResponse)
async def approve_shadow_candidate(candidate_id: UUID, request: ShadowCandidateDecisionRequest, db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin)):
    try:
        row = await ShadowMemoryPublicationService(db).approve(candidate_id=candidate_id, actor_id=UUID(user.id), reason=request.reason,
            content=request.content, scope=request.scope, project_id=request.project_id,
            scope_ids=request.scope_ids, promote_to_company=request.promote_to_company)
        await db.commit()
    except ValueError as exc:
        await db.rollback(); raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
        candidate_type=row.candidate_type, subject=row.subject, content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
        scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence)


@router.post("/staging/candidates/{candidate_id}/reject", response_model=ShadowCandidateResponse)
async def reject_shadow_candidate(candidate_id: UUID, request: ShadowCandidateDecisionRequest, db: AsyncSession = Depends(db_session), user: UserCtx = Depends(require_admin)):
    try:
        row = await ShadowMemoryPublicationService(db).reject(candidate_id=candidate_id, actor_id=UUID(user.id), reason=request.reason)
        await db.commit()
    except ValueError as exc:
        await db.rollback(); raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ShadowCandidateResponse(id=row.id, snapshot_id=row.snapshot_id, visibility_tenant_id=row.visibility_tenant_id,
        candidate_type=row.candidate_type, subject=row.subject, content=dict(row.content or {}), evidence_section_ids=list(row.evidence_section_ids or []),
        scope_candidate=row.scope_candidate, resolution_status=row.resolution_status, extraction_confidence=row.extraction_confidence)


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
