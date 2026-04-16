"""
Repository for SystemLLMRole operations.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models.system_llm_role import SystemLLMRole, SystemLLMRoleType


class SystemLLMRoleRepository:
    """Repository for SystemLLMRole database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, role: SystemLLMRole) -> SystemLLMRole:
        """Create a new SystemLLMRole."""
        self.session.add(role)
        await self.session.flush()
        return role
    
    async def get_by_id(self, role_id: UUID) -> Optional[SystemLLMRole]:
        """Get SystemLLMRole by ID."""
        result = await self.session.execute(
            select(SystemLLMRole).where(SystemLLMRole.id == role_id)
        )
        return result.scalar_one_or_none()
    
    async def get_active_role(self, role_type: SystemLLMRoleType) -> Optional[SystemLLMRole]:
        """Get the active role for the specified type."""
        result = await self.session.execute(
            select(SystemLLMRole).where(
                and_(
                    SystemLLMRole.role_type == role_type,
                    SystemLLMRole.is_active.is_(True)
                )
            )
        )
        role = result.scalar_one_or_none()
        if role:
            await self.session.refresh(role)
        return role
    
    async def get_all_roles(self) -> List[SystemLLMRole]:
        """Get all SystemLLMRole entries."""
        result = await self.session.execute(
            select(SystemLLMRole).order_by(SystemLLMRole.role_type, SystemLLMRole.created_at)
        )
        return result.scalars().all()
    
    async def get_roles_by_type(self, role_type: SystemLLMRoleType) -> List[SystemLLMRole]:
        """Get all roles of a specific type."""
        result = await self.session.execute(
            select(SystemLLMRole)
            .where(SystemLLMRole.role_type == role_type)
            .order_by(SystemLLMRole.created_at.desc())
        )
        return result.scalars().all()
    
    async def update(self, role: SystemLLMRole) -> SystemLLMRole:
        """Update a SystemLLMRole."""
        await self.session.merge(role)
        await self.session.flush()
        return role
    
    async def delete(self, role_id: UUID) -> bool:
        """Delete a SystemLLMRole."""
        result = await self.session.execute(
            select(SystemLLMRole).where(SystemLLMRole.id == role_id)
        )
        role = result.scalar_one_or_none()
        if role:
            await self.session.delete(role)
            await self.session.flush()
            return True
        return False
    
    async def activate_role(self, role_id: UUID) -> Optional[SystemLLMRole]:
        """Activate a role and deactivate all other roles of the same type."""
        # Get the role to activate
        role = await self.get_by_id(role_id)
        if not role:
            return None
        
        # Deactivate all other roles of the same type
        result = await self.session.execute(
            select(SystemLLMRole).where(
                and_(
                    SystemLLMRole.role_type == role.role_type,
                    SystemLLMRole.id != role_id
                )
            )
        )
        other_roles = result.scalars().all()
        
        for other_role in other_roles:
            other_role.is_active = False
        
        # Activate the target role
        role.is_active = True
        
        await self.session.flush()
        return role
