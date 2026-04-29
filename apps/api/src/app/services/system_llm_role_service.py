"""
Service for SystemLLMRole business logic.
"""
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    SystemLLMRoleNotFoundError,
    SystemLLMRoleValidationError,
    AppError as SystemLLMRoleError,
)
from app.models.system_llm_role import SystemLLMRole, SystemLLMRoleType
from app.repositories.system_llm_role_repository import SystemLLMRoleRepository
from app.schemas.system_llm_roles import (
    SystemLLMRoleCreate, SystemLLMRoleUpdate,
    TriageRoleUpdate, PlannerRoleUpdate, SummaryRoleUpdate, MemoryRoleUpdate
)

logger = logging.getLogger(__name__)


class SystemLLMRoleService:
    """Service for SystemLLMRole business operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SystemLLMRoleRepository(session)
    
    async def create_role(self, data: SystemLLMRoleCreate) -> SystemLLMRole:
        """Create a new SystemLLMRole."""
        # Check if active role already exists for this type
        existing_active = await self.repo.get_active_role(data.role_type)
        if existing_active and data.is_active:
            # If creating an active role, deactivate existing one
            existing_active.is_active = False
        
        role = SystemLLMRole(**data.model_dump())
        return await self.repo.create(role)
    
    async def get_role(self, role_id: UUID) -> SystemLLMRole:
        """Get a role by ID."""
        role = await self.repo.get_by_id(role_id)
        if not role:
            raise SystemLLMRoleNotFoundError(f"Role {role_id} not found")
        return role
    
    async def get_active_role(self, role_type: SystemLLMRoleType) -> Optional[SystemLLMRole]:
        """Get the active role for the specified type."""
        return await self.repo.get_active_role(role_type)
    
    async def get_all_roles(self) -> List[SystemLLMRole]:
        """Get all roles."""
        return await self.repo.get_all_roles()
    
    async def get_roles_by_type(self, role_type: SystemLLMRoleType) -> List[SystemLLMRole]:
        """Get all roles of a specific type."""
        return await self.repo.get_roles_by_type(role_type)
    
    async def update_role(self, role_id: UUID, data: SystemLLMRoleUpdate) -> SystemLLMRole:
        """Update a role."""
        role = await self.get_role(role_id)
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)
        
        return await self.repo.update(role)
    
    async def _update_role_by_type(
        self,
        role_type: SystemLLMRoleType,
        data: TriageRoleUpdate,
    ) -> Optional[SystemLLMRole]:
        """Update the active role of the given type. Creates if not found."""
        role = await self.repo.get_active_role(role_type)
        if not role:
            role = SystemLLMRole(role_type=role_type, is_active=True)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(role, field):
                setattr(role, field, value)

        return await self.repo.update(role)

    async def update_triage_role(self, data: TriageRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Triage role."""
        return await self._update_role_by_type(SystemLLMRoleType.TRIAGE, data)

    async def update_planner_role(self, data: PlannerRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Planner role."""
        return await self._update_role_by_type(SystemLLMRoleType.PLANNER, data)

    async def update_summary_role(self, data: SummaryRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Summary role."""
        return await self._update_role_by_type(SystemLLMRoleType.SUMMARY, data)

    async def update_memory_role(self, data: MemoryRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Memory role."""
        return await self._update_role_by_type(SystemLLMRoleType.MEMORY, data)
    
    async def delete_role(self, role_id: UUID) -> bool:
        """Delete a role."""
        return await self.repo.delete(role_id)
    
    async def activate_role(self, role_id: UUID) -> SystemLLMRole:
        """Activate a role and deactivate others of the same type."""
        role = await self.repo.activate_role(role_id)
        if not role:
            raise SystemLLMRoleNotFoundError(f"Role {role_id} not found")
        return role
    
    async def get_role_config(self, role_type: SystemLLMRoleType) -> Dict[str, Any]:
        """Get role configuration as a dictionary for execution."""
        role = await self.repo.get_active_role(role_type)
        if not role:
            raise SystemLLMRoleNotFoundError(f"No active {role_type} role found")
        
        config = {
            'id': str(role.id),
            'role_type': role.role_type,
            'prompt': role.compiled_prompt,
            'model': role.model,
            'temperature': role.temperature,
            'max_tokens': role.max_tokens,
            'timeout_s': role.timeout_s,
            'max_retries': role.max_retries,
            'retry_backoff': role.retry_backoff,
        }
        
        logger.info(f"Role config for {role_type}: model={config['model']}, temperature={config['temperature']}")
        return config
    
    async def ensure_default_roles(self) -> Dict[SystemLLMRoleType, SystemLLMRole]:
        """Ensure default roles exist and return them."""
        default_roles = {}
        
        default_configs = self._get_default_configs()
        for role_type in SystemLLMRoleType:
            role = await self.repo.get_active_role(role_type)
            config = default_configs.get(role_type, {})
            if not role:
                role = SystemLLMRole(
                    role_type=role_type,
                    is_active=True,
                    **config
                )
                role = await self.repo.create(role)
                logger.info(f"Created default {role_type.value} role")
            else:
                # Sync prompt-related fields so changes in v3_role_defaults propagate.
                updated = False
                for field in ("identity", "mission", "rules", "safety", "output_requirements"):
                    new_val = config.get(field)
                    if new_val is not None and getattr(role, field, None) != new_val:
                        setattr(role, field, new_val)
                        updated = True
                if updated:
                    role = await self.repo.update(role)
                    logger.info(f"Updated prompt fields for {role_type.value} role")

            default_roles[role_type] = role
        
        return default_roles
    
    def _get_default_configs(self) -> Dict[SystemLLMRoleType, Dict[str, Any]]:
        """Get default configurations for each role type (v3 canonical copy)."""
        from app.services.v3_role_defaults import V3_ROLE_DEFAULTS
        # Shallow copy so callers may safely mutate the result.
        return {rt: dict(cfg) for rt, cfg in V3_ROLE_DEFAULTS.items()}
