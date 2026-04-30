"""
Admin API router for SystemLLMRole management.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_service import (
    SystemLLMRoleService, SystemLLMRoleNotFoundError
)
from app.schemas.system_llm_roles import (
    SystemLLMRoleCreate, SystemLLMRoleUpdate, SystemLLMRoleResponse,
    TriageRoleUpdate, PlannerRoleUpdate, SummaryRoleUpdate, MemoryRoleUpdate,
    SynthesizerRoleUpdate, FactExtractorRoleUpdate, SummaryCompactorRoleUpdate,
)

router = APIRouter(prefix="/system-llm-roles", tags=["system-llm-roles"])


@router.get("", response_model=List[SystemLLMRoleResponse])
async def list_roles(
    role_type: SystemLLMRoleType = Query(None, description="Filter by role type"),
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """List all system LLM roles, optionally filtered by type."""
    service = SystemLLMRoleService(session)
    
    if role_type:
        roles = await service.get_roles_by_type(role_type)
    else:
        roles = await service.get_all_roles()
    
    return roles


@router.get("/{role_id}", response_model=SystemLLMRoleResponse)
async def get_role(
    role_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Get a specific system LLM role."""
    service = SystemLLMRoleService(session)
    role = await service.get_role(role_id)
    return role


@router.get("/active/{role_type}", response_model=SystemLLMRoleResponse)
async def get_active_role(
    role_type: SystemLLMRoleType,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Get the active role for the specified type."""
    service = SystemLLMRoleService(session)
    role = await service.get_active_role(role_type)
    
    if not role:
        raise HTTPException(status_code=404, detail=f"No active {role_type.value} role found")
    
    return role


@router.post("", response_model=SystemLLMRoleResponse)
async def create_role(
    data: SystemLLMRoleCreate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Create a new system LLM role."""
    service = SystemLLMRoleService(session)
    role = await service.create_role(data)
    return role


@router.put("/{role_id}", response_model=SystemLLMRoleResponse)
async def update_role(
    role_id: UUID,
    data: SystemLLMRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update a system LLM role."""
    service = SystemLLMRoleService(session)
    role = await service.update_role(role_id, data)
    return role


@router.delete("/{role_id}")
async def delete_role(
    role_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Delete a system LLM role."""
    service = SystemLLMRoleService(session)
    success = await service.delete_role(role_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return {"message": "Role deleted successfully"}


@router.post("/{role_id}/activate", response_model=SystemLLMRoleResponse)
async def activate_role(
    role_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Activate a role and deactivate others of the same type."""
    service = SystemLLMRoleService(session)
    role = await service.activate_role(role_id)
    return role


# === Role-specific update endpoints ===
# All accept SystemLLMRoleUpdate with real DB column names:
# identity, mission, rules, safety, output_requirements, model, temperature, etc.

@router.patch("/triage", response_model=SystemLLMRoleResponse)
async def update_triage_role(
    data: TriageRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Triage role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_triage_role(data)
    await session.commit()
    return role


@router.patch("/planner", response_model=SystemLLMRoleResponse)
async def update_planner_role(
    data: PlannerRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Planner role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_planner_role(data)
    await session.commit()
    return role


@router.patch("/summary", response_model=SystemLLMRoleResponse)
async def update_summary_role(
    data: SummaryRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Summary role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_summary_role(data)
    await session.commit()
    return role


@router.patch("/memory", response_model=SystemLLMRoleResponse)
async def update_memory_role(
    data: MemoryRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Memory role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_memory_role(data)
    await session.commit()
    return role


@router.patch("/synthesizer", response_model=SystemLLMRoleResponse)
async def update_synthesizer_role(
    data: SynthesizerRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Synthesizer role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_synthesizer_role(data)
    await session.commit()
    return role


@router.patch("/fact-extractor", response_model=SystemLLMRoleResponse)
async def update_fact_extractor_role(
    data: FactExtractorRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Fact Extractor role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_fact_extractor_role(data)
    await session.commit()
    return role


@router.patch("/summary-compactor", response_model=SystemLLMRoleResponse)
async def update_summary_compactor_role(
    data: SummaryCompactorRoleUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Update the active Summary Compactor role configuration."""
    service = SystemLLMRoleService(session)
    role = await service.update_summary_compactor_role(data)
    await session.commit()
    return role


@router.post("/ensure-defaults")
async def ensure_default_roles(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin)
):
    """Ensure default roles exist and create them if needed."""
    service = SystemLLMRoleService(session)
    roles = await service.ensure_default_roles()
    await session.commit()
    
    return {
        "message": "Default roles ensured",
        "roles": {
            role_type.value: str(role.id)
            for role_type, role in roles.items()
        }
    }
