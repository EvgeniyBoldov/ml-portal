"""Read-only endpoints for the virtual Project Memory collection."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers.collections.crud import _resolve_requested_tenant_id
from app.core.security import UserCtx
from app.services.project_memory_catalog_service import (
    ProjectMemoryCatalogService,
    ProjectMemoryProject,
)

router = APIRouter(prefix="/project-memory")


class ProjectMemoryProjectResponse(BaseModel):
    key: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ProjectMemoryOverviewResponse(BaseModel):
    projects: list[ProjectMemoryProjectResponse]
    total: int


class ProjectMemoryFactResponse(BaseModel):
    subject: str
    value: str
    kind: str
    status: str
    observed_at: datetime


class ProjectMemoryProjectDetailResponse(BaseModel):
    project: ProjectMemoryProjectResponse
    facts: list[ProjectMemoryFactResponse]


def _project_response(project: ProjectMemoryProject) -> ProjectMemoryProjectResponse:
    return ProjectMemoryProjectResponse(
        key=project.key,
        name=project.name,
        aliases=list(project.aliases),
        status_counts=project.status_counts,
        updated_at=project.updated_at,
    )


@router.get("", response_model=ProjectMemoryOverviewResponse)
async def get_project_memory_overview(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    projects = await ProjectMemoryCatalogService(session).list_projects(tenant_id=tenant_id)
    return ProjectMemoryOverviewResponse(
        projects=[_project_response(project) for project in projects],
        total=len(projects),
    )


@router.get("/projects/{project_key}", response_model=ProjectMemoryProjectDetailResponse)
async def get_project_memory_project(
    project_key: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    detail = await ProjectMemoryCatalogService(session).get_project(
        tenant_id=tenant_id,
        project_key=project_key,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Project memory not found")
    return ProjectMemoryProjectDetailResponse(
        project=_project_response(detail.project),
        facts=[
            ProjectMemoryFactResponse(
                subject=fact.subject,
                value=fact.value,
                kind=fact.kind,
                status=fact.status,
                observed_at=fact.observed_at,
            )
            for fact in detail.facts
        ],
    )
