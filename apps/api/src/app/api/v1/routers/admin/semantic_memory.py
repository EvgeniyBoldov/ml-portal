"""Admin inspection endpoints for document-derived semantic memory."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus, Source
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.semantic_memory_admin_service import (
    SemanticMemoryAdminService,
    SemanticMemoryListRow,
)


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


def _item_response(row: SemanticMemoryListRow) -> SemanticMemoryItemResponse:
    item = row.item
    return SemanticMemoryItemResponse(
        id=item.id, scope=item.scope, item_type=item.item_type, project_id=item.project_id,
        subject=item.subject, content_text=item.content_text, content=dict(item.content or {}), confidence=item.confidence,
        state=item.state, applicability=dict(item.applicability or {}), visibility=dict(item.visibility or {}),
        last_verified_at=item.last_verified_at, updated_at=item.updated_at,
        source_count=row.source_count, claim_count=row.claim_count,
    )


@router.get("", response_model=SemanticMemoryPageResponse)
async def list_semantic_memory(
    scope: str | None = Query(default=None, pattern="^(company|project)$"),
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
    status = (await db.execute(select(RAGStatus).where(
        RAGStatus.doc_id == document_id, RAGStatus.node_type == "memory", RAGStatus.node_key == "extract",
    ))).scalar_one_or_none()
    return SemanticMemoryExtractionStatusResponse(
        document_id=document_id,
        status=status.status if status is not None else "not_queued",
        metrics=dict(status.metrics_json or {}) if status is not None else {},
    )


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
    return SemanticMemoryDetailResponse(
        **base,
        sources=[SemanticMemorySourceResponse(
            document_id=item.document_id, canonical_checksum=item.canonical_checksum,
            section_id=item.section_id, label=item.label,
            start_offset=item.start_offset, end_offset=item.end_offset,
        ) for item in detail.sources],
        claims=[SemanticMemoryClaimResponse(
            id=item.id, document_id=item.document_id, canonical_checksum=item.canonical_checksum,
            scope=item.scope, item_type=item.item_type, project_id=item.project_id,
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
    """Queue a source-backed re-extraction; semantic content is never edited inline."""
    document = await db.get(RAGDocument, document_id)
    source = (await db.execute(select(Source).where(Source.source_id == document_id))).scalar_one_or_none()
    if document is None or source is None:
        raise HTTPException(status_code=404, detail="Document source not found")
    enabled = bool((source.meta or {}).get("memory", {}).get("enabled"))
    if document.status == "archived" or not document.s3_key_processed or not enabled:
        raise HTTPException(status_code=409, detail="Document is not eligible for memory extraction")
    status = (await db.execute(select(RAGStatus).where(
        RAGStatus.doc_id == document_id, RAGStatus.node_type == "memory", RAGStatus.node_key == "extract",
    ))).scalar_one_or_none()
    if status is not None and status.status in {"queued", "processing"}:
        return {"document_id": str(document_id), "status": "queued"}
    tenant_id = source.tenant_id or document.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=409, detail="Document has no tenant execution context")
    await RAGStatusManager(db, AsyncRepositoryFactory(db, tenant_id)).transition_stage(
        document_id, "memory.extract", StageStatus.QUEUED,
    )
    await db.commit()
    from app.workers.tasks_rag_ingest.document_memory import extract_document_memory
    extract_document_memory.delay({"source_id": str(document.id), "canonical_key": str(document.s3_key_processed)}, str(tenant_id), True)
    return {"document_id": str(document_id), "status": "queued"}
