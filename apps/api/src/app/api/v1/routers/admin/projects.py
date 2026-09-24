"""Admin catalogue for company external projects."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.project import Project
from app.models.memory_scope import MemoryScope

router = APIRouter(prefix="/projects")


class ProjectInput(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class ProjectResponse(ProjectInput):
    id: UUID
    is_active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return list((await db.execute(select(Project).order_by(Project.name))).scalars().all())


@router.post("", response_model=ProjectResponse)
async def create_project(data: ProjectInput, db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    key = data.key.strip().lower()
    if key == "all":
        raise HTTPException(status_code=422, detail="Project key 'all' is reserved for the aggregate scope")
    exists = await db.execute(select(Project.id).where(Project.key == key))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Project key already exists")
    project = Project(key=key, name=data.name.strip(), aliases=[item.strip() for item in data.aliases if item.strip()], description=data.description)
    db.add(project)
    await db.flush()
    scope = (await db.execute(select(MemoryScope).where(MemoryScope.key == f"project.{key}"))).scalar_one_or_none()
    if scope is None:
        db.add(MemoryScope(scope_type="project", key=f"project.{key}", name=project.name,
                           aliases=list(project.aliases), project_id=project.id))
    elif scope.scope_type == "project" and scope.project_id is None:
        if scope.lifecycle_status != "active":
            raise HTTPException(status_code=409, detail="Project memory scope is scheduled for deletion")
        scope.project_id = project.id
    else:
        raise HTTPException(status_code=409, detail="Project memory scope is already linked")
    await db.commit()
    await db.refresh(project)
    return project
