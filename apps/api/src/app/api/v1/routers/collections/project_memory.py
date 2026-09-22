"""Read-only virtual Project Memory collection backed by semantic memory."""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers.collections.crud import _resolve_requested_tenant_id
from app.core.security import UserCtx
from app.models.memory import MemoryClaim, MemoryItem
from app.models.project import Project
from app.models.rag import RAGDocument
from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.runtime.memory.document_memory import split_canonical_sections


router = APIRouter(prefix="/project-memory")
global_router = APIRouter(prefix="/global-memory")


class ProjectMemoryProjectResponse(BaseModel):
    key: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ProjectMemoryItemResponse(BaseModel):
    id: UUID
    subject: str
    value: str
    content: dict[str, object] = Field(default_factory=dict)
    kind: str
    status: str
    observed_at: datetime
    last_verified_at: datetime
    applicability: dict[str, object] = Field(default_factory=dict)
    source_count: int = 0
    evidence_section_ids: list[str] = Field(default_factory=list)


class ProjectMemoryOverviewResponse(BaseModel):
    projects: list[ProjectMemoryProjectResponse]
    total: int


class ProjectCatalogItemResponse(BaseModel):
    key: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class ProjectMemoryProjectDetailResponse(BaseModel):
    project: ProjectMemoryProjectResponse
    items: list[ProjectMemoryItemResponse]
    total: int = 0
    limit: int = 100
    offset: int = 0


class GlobalMemoryOverviewResponse(BaseModel):
    items: list[ProjectMemoryItemResponse]
    total: int
    limit: int = 100
    offset: int = 0


class ProjectMemoryEvidencePreviewResponse(BaseModel):
    document_id: UUID
    section_id: str
    label: str
    start_offset: int
    end_offset: int
    excerpt: str


def _visible_claim_filter(tenant_id: UUID):
    return and_(
        or_(MemoryClaim.visibility_tenant_id.is_(None), MemoryClaim.visibility_tenant_id == tenant_id),
        RAGDocument.status != "archived",
        or_(RAGDocument.scope == "global", RAGDocument.tenant_id == tenant_id),
    )


@router.get("/catalog", response_model=list[ProjectCatalogItemResponse])
async def get_project_catalog(
    session: AsyncSession = Depends(db_uow), user: UserCtx = Depends(get_current_user),
):
    """The company project catalogue is intentionally independent of tenant memory visibility."""
    await _resolve_requested_tenant_id(session, user, None)
    projects = (await session.execute(
        select(Project).where(Project.is_active.is_(True)).order_by(Project.name)
    )).scalars().all()
    return [ProjectCatalogItemResponse(key=p.key, name=p.name, aliases=list(p.aliases or [])) for p in projects]


def _effective_item_rows(rows: list[tuple[MemoryItem, MemoryClaim]]) -> list[tuple[MemoryItem, MemoryClaim, int, str]]:
    """Project the content from claims already visible to the caller.

    A MemoryItem is shared identity and may have a consolidated winner from a
    different department.  Returning that winner here would disclose private
    source text, so the virtual collection must select only visible claims.
    """
    grouped: dict[UUID, tuple[MemoryItem, list[MemoryClaim]]] = {}
    for item, claim in rows:
        current = grouped.setdefault(item.id, (item, []))
        current[1].append(claim)
    result: list[tuple[MemoryItem, MemoryClaim, int, str]] = []
    for item, claims in grouped.values():
        active = [claim for claim in claims if claim.state == "active"]
        conflicts = [claim for claim in claims if claim.state == "conflict"]
        ranked = active or conflicts or claims
        ranked.sort(key=lambda claim: (claim.confidence, claim.updated_at), reverse=True)
        winner = ranked[0]
        if active:
            state = "uncertain" if conflicts or len({claim.content_text for claim in active}) > 1 else "active"
        elif conflicts:
            state = "uncertain"
        else:
            state = "stale"
        result.append((item, winner, len({claim.document_id for claim in claims}), state))
    return result


@global_router.get("", response_model=GlobalMemoryOverviewResponse)
async def get_global_memory_overview(
    session: AsyncSession = Depends(db_uow), user: UserCtx = Depends(get_current_user),
    query: str | None = Query(default=None, max_length=200),
    item_type: str | None = Query(default=None, pattern="^(description|relationship|rule|constraint|procedure|decision)$"),
    state: str | None = Query(default=None, pattern="^(active|uncertain|stale)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    rows = (await session.execute(
        select(MemoryItem, MemoryClaim)
        .join(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
        .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
        .where(MemoryItem.scope == "company", _visible_claim_filter(tenant_id))
        .order_by(MemoryItem.updated_at.desc(), MemoryItem.subject)
    )).all()
    effective = _effective_item_rows(rows)
    normalized = (query or "").strip().casefold()
    filtered = [row for row in effective if (
        (not normalized or normalized in row[0].subject.casefold() or normalized in row[1].content_text.casefold())
        and (item_type is None or row[0].item_type == item_type)
        and (state is None or row[3] == state)
    )]
    page = filtered[offset:offset + limit]
    return GlobalMemoryOverviewResponse(
        items=[ProjectMemoryItemResponse(
            id=item.id, subject=item.subject, value=claim.content_text,
            content=dict(claim.content or {}), kind=item.item_type, status=item_state,
            observed_at=item.last_verified_at, last_verified_at=item.last_verified_at,
            applicability=dict(claim.applicability or {}), source_count=source_count,
            evidence_section_ids=list(claim.evidence_section_ids or []),
        ) for item, claim, source_count, item_state in page],
        total=len(filtered), limit=limit, offset=offset,
    )


async def _project_summary(session: AsyncSession, project: Project, tenant_id: UUID) -> ProjectMemoryProjectResponse:
    rows = (await session.execute(
        select(MemoryItem, MemoryClaim)
        .join(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
        .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
        .where(
            MemoryItem.scope == "project", MemoryItem.project_id == project.id,
            _visible_claim_filter(tenant_id),
        )
    )).all()
    effective = _effective_item_rows(rows)
    counts: dict[str, int] = {}
    for item, _claim, _source_count, state in effective:
        counts[state] = counts.get(state, 0) + 1
    updated_at = max((item.updated_at for item, _claim, _source_count, _state in effective), default=None)
    return ProjectMemoryProjectResponse(
        key=project.key, name=project.name, aliases=list(project.aliases or []),
        status_counts=counts, updated_at=updated_at,
    )


@router.get("", response_model=ProjectMemoryOverviewResponse)
async def get_project_memory_overview(
    session: AsyncSession = Depends(db_uow), user: UserCtx = Depends(get_current_user),
    query: str | None = Query(default=None, max_length=200),
    state: str | None = Query(default=None, pattern="^(active|uncertain|stale)$"),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    project_ids = (await session.execute(
        select(MemoryItem.project_id).distinct()
        .join(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
        .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
        .where(
            MemoryItem.scope == "project", MemoryItem.project_id.is_not(None),
            _visible_claim_filter(tenant_id),
        )
    )).scalars().all()
    projects = (await session.execute(
        select(Project).where(Project.id.in_(project_ids), Project.is_active.is_(True)).order_by(Project.name)
    )).scalars().all() if project_ids else []
    rows = [await _project_summary(session, project, tenant_id) for project in projects]
    normalized = (query or "").strip().casefold()
    rows = [row for row in rows if (
        not normalized or normalized in row.name.casefold()
        or normalized in row.key.casefold()
        or any(normalized in alias.casefold() for alias in row.aliases)
    ) and (state is None or row.status_counts.get(state, 0) > 0)]
    return ProjectMemoryOverviewResponse(projects=rows, total=sum(sum(row.status_counts.values()) for row in rows))


@router.get("/projects/{project_key}", response_model=ProjectMemoryProjectDetailResponse)
async def get_project_memory_project(
    project_key: str,
    session: AsyncSession = Depends(db_uow), user: UserCtx = Depends(get_current_user),
    query: str | None = Query(default=None, max_length=200),
    item_type: str | None = Query(default=None, pattern="^(description|relationship|rule|constraint|procedure|decision)$"),
    state: str | None = Query(default=None, pattern="^(active|uncertain|stale)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    project = (await session.execute(select(Project).where(
        Project.key == project_key.strip().lower(), Project.is_active.is_(True),
    ))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = (await session.execute(
        select(MemoryItem, MemoryClaim)
        .join(MemoryClaim, MemoryClaim.memory_item_id == MemoryItem.id)
        .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
        .where(
            MemoryItem.scope == "project", MemoryItem.project_id == project.id,
            _visible_claim_filter(tenant_id),
        )
        .order_by(MemoryItem.updated_at.desc(), MemoryItem.subject)
    )).all()
    effective = _effective_item_rows(rows)
    normalized = (query or "").strip().casefold()
    filtered = [row for row in effective if (
        (not normalized or normalized in row[0].subject.casefold() or normalized in row[1].content_text.casefold())
        and (item_type is None or row[0].item_type == item_type)
        and (state is None or row[3] == state)
    )]
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return ProjectMemoryProjectDetailResponse(
        project=await _project_summary(session, project, tenant_id),
        items=[ProjectMemoryItemResponse(
            id=item.id, subject=item.subject, value=claim.content_text, kind=item.item_type,
            content=dict(claim.content or {}),
            status=state, observed_at=item.last_verified_at, last_verified_at=item.last_verified_at,
            applicability=dict(claim.applicability or {}), source_count=source_count,
            evidence_section_ids=list(claim.evidence_section_ids or []),
        ) for item, claim, source_count, state in page],
        total=total, limit=limit, offset=offset,
    )


@router.get("/items/{item_id}/evidence/{section_id}", response_model=ProjectMemoryEvidencePreviewResponse)
async def get_project_memory_evidence_preview(
    item_id: UUID,
    section_id: str,
    session: AsyncSession = Depends(db_uow), user: UserCtx = Depends(get_current_user),
):
    """Return one bounded canonical section only after claim/document ACL filtering."""
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    row = (await session.execute(
        select(MemoryClaim, RAGDocument)
        .join(RAGDocument, RAGDocument.id == MemoryClaim.document_id)
        .where(
            MemoryClaim.memory_item_id == item_id,
            MemoryClaim.evidence_section_ids.contains([section_id]),
            _visible_claim_filter(tenant_id),
        )
        .order_by(MemoryClaim.updated_at.desc())
        .limit(1)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    _claim, document = row
    if not document.s3_key_processed:
        raise HTTPException(status_code=404, detail="Evidence not found")
    payload = await s3_manager.get_object(get_settings().S3_BUCKET_RAG, document.s3_key_processed)
    if not payload:
        raise HTTPException(status_code=404, detail="Evidence not found")
    try:
        canonical = json.loads(payload.decode("utf-8"))
        section = next((item for item in split_canonical_sections(str(canonical.get("text") or "")) if item["id"] == section_id), None)
    except (UnicodeDecodeError, json.JSONDecodeError):
        section = None
    if section is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return ProjectMemoryEvidencePreviewResponse(
        document_id=document.id, section_id=section_id, label=str(section["label"]),
        start_offset=int(section["start_offset"]), end_offset=int(section["end_offset"]),
        excerpt=str(section["text"]),
    )
