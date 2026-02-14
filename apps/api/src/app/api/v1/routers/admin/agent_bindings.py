"""
Admin agent bindings router — CRUD for tool bindings per agent version.

Endpoints:
- GET    /agents/{slug}/versions/{version}/bindings       — list bindings
- POST   /agents/{slug}/versions/{version}/bindings       — create binding
- PATCH  /agents/{slug}/versions/{version}/bindings/{id}  — update binding
- DELETE /agents/{slug}/versions/{version}/bindings/{id}  — delete binding
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.agent_binding import AgentBinding
from app.models.tool import Tool
from app.models.tool_instance import ToolInstance
from app.models.tool_group import ToolGroup
from app.services.agent_service import (
    AgentService,
    AgentNotFoundError,
    AgentVersionNotFoundError,
)
from app.schemas.agent_bindings import (
    AgentBindingCreate,
    AgentBindingUpdate,
    AgentBindingDetailResponse,
)

router = APIRouter(tags=["agent-bindings"])


async def _get_version_id(
    slug: str, version_number: int, db: AsyncSession
) -> UUID:
    """Resolve agent version ID from slug + version number."""
    service = AgentService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        return version.id
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentVersionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _enrich_binding(
    binding: AgentBinding, db: AsyncSession
) -> dict:
    """Build detail response with tool/instance info."""
    tool_slug = None
    tool_name = None
    tool_group_slug = None
    instance_slug = None
    instance_name = None

    if binding.tool_id:
        result = await db.execute(
            select(Tool.slug, Tool.name, Tool.tool_group_id).where(Tool.id == binding.tool_id)
        )
        row = result.one_or_none()
        if row:
            tool_slug = row.slug
            tool_name = row.name
            if row.tool_group_id:
                grp = await db.execute(
                    select(ToolGroup.slug).where(ToolGroup.id == row.tool_group_id)
                )
                grp_row = grp.scalar_one_or_none()
                tool_group_slug = grp_row if grp_row else None

    if binding.tool_instance_id:
        result = await db.execute(
            select(ToolInstance.slug, ToolInstance.name).where(
                ToolInstance.id == binding.tool_instance_id
            )
        )
        row = result.one_or_none()
        if row:
            instance_slug = row.slug
            instance_name = row.name

    return {
        "id": binding.id,
        "agent_version_id": binding.agent_version_id,
        "tool_id": binding.tool_id,
        "tool_instance_id": binding.tool_instance_id,
        "credential_strategy": binding.credential_strategy,
        "created_at": binding.created_at,
        "tool_slug": tool_slug,
        "tool_name": tool_name,
        "tool_group_slug": tool_group_slug,
        "instance_slug": instance_slug,
        "instance_name": instance_name,
    }


@router.get(
    "/{slug}/versions/{version_number}/bindings",
    response_model=List[AgentBindingDetailResponse],
)
async def list_bindings(
    slug: str,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool bindings for an agent version."""
    version_id = await _get_version_id(slug, version_number, db)

    result = await db.execute(
        select(AgentBinding)
        .where(AgentBinding.agent_version_id == version_id)
        .order_by(AgentBinding.created_at)
    )
    bindings = result.scalars().all()

    return [await _enrich_binding(b, db) for b in bindings]


@router.post(
    "/{slug}/versions/{version_number}/bindings",
    response_model=AgentBindingDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_binding(
    slug: str,
    version_number: int,
    data: AgentBindingCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool binding for an agent version."""
    version_id = await _get_version_id(slug, version_number, db)

    # Validate tool exists
    tool = await db.execute(select(Tool).where(Tool.id == data.tool_id))
    if not tool.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Tool '{data.tool_id}' not found")

    # Validate instance exists (if provided)
    if data.tool_instance_id:
        inst = await db.execute(
            select(ToolInstance).where(ToolInstance.id == data.tool_instance_id)
        )
        if not inst.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail=f"Tool instance '{data.tool_instance_id}' not found",
            )

    # Check duplicate
    existing = await db.execute(
        select(AgentBinding).where(
            AgentBinding.agent_version_id == version_id,
            AgentBinding.tool_id == data.tool_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Binding for this tool already exists in this version",
        )

    binding = AgentBinding(
        agent_version_id=version_id,
        tool_id=data.tool_id,
        tool_instance_id=data.tool_instance_id,
        credential_strategy=data.credential_strategy.value,
    )
    db.add(binding)
    await db.flush()
    await db.commit()

    return await _enrich_binding(binding, db)


@router.patch(
    "/{slug}/versions/{version_number}/bindings/{binding_id}",
    response_model=AgentBindingDetailResponse,
)
async def update_binding(
    slug: str,
    version_number: int,
    binding_id: UUID,
    data: AgentBindingUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update an existing tool binding."""
    version_id = await _get_version_id(slug, version_number, db)

    result = await db.execute(
        select(AgentBinding).where(
            AgentBinding.id == binding_id,
            AgentBinding.agent_version_id == version_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")

    if data.tool_instance_id is not None:
        if data.tool_instance_id:
            inst = await db.execute(
                select(ToolInstance).where(ToolInstance.id == data.tool_instance_id)
            )
            if not inst.scalar_one_or_none():
                raise HTTPException(
                    status_code=404,
                    detail=f"Tool instance '{data.tool_instance_id}' not found",
                )
        binding.tool_instance_id = data.tool_instance_id

    if data.credential_strategy is not None:
        binding.credential_strategy = data.credential_strategy.value

    await db.flush()
    await db.commit()

    return await _enrich_binding(binding, db)


@router.delete(
    "/{slug}/versions/{version_number}/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_binding(
    slug: str,
    version_number: int,
    binding_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a tool binding."""
    version_id = await _get_version_id(slug, version_number, db)

    result = await db.execute(
        select(AgentBinding).where(
            AgentBinding.id == binding_id,
            AgentBinding.agent_version_id == version_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")

    await db.delete(binding)
    await db.commit()
