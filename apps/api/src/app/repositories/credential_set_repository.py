"""
CredentialSet Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential_set import CredentialSet, CredentialScope


class CredentialSetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, cred_set: CredentialSet) -> CredentialSet:
        self.session.add(cred_set)
        await self.session.flush()
        await self.session.refresh(cred_set)
        return cred_set

    async def get_by_id(self, cred_id: UUID) -> Optional[CredentialSet]:
        stmt = select(CredentialSet).where(CredentialSet.id == cred_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, cred_set: CredentialSet) -> CredentialSet:
        self.session.add(cred_set)
        await self.session.flush()
        await self.session.refresh(cred_set)
        return cred_set

    async def delete(self, cred_set: CredentialSet) -> None:
        await self.session.delete(cred_set)
        await self.session.flush()

    async def list_credentials(
        self,
        skip: int = 0,
        limit: int = 100,
        tool_instance_id: Optional[UUID] = None,
        scope: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[CredentialSet], int]:
        """List credential sets with filters"""
        stmt = select(CredentialSet)
        
        if tool_instance_id:
            stmt = stmt.where(CredentialSet.tool_instance_id == tool_instance_id)
        if scope:
            stmt = stmt.where(CredentialSet.scope == scope)
        if tenant_id:
            stmt = stmt.where(CredentialSet.tenant_id == tenant_id)
        if is_active is not None:
            stmt = stmt.where(CredentialSet.is_active == is_active)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(CredentialSet.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def get_for_instance(
        self,
        tool_instance_id: UUID,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[CredentialSet]:
        """
        Get credentials for a tool instance following priority:
        User > Tenant
        
        Args:
            tool_instance_id: ID of the tool instance
            user_id: User ID (for user-level credentials)
            tenant_id: Tenant ID (for tenant-level credentials)
            
        Returns:
            CredentialSet or None if no credentials found
        """
        conditions = [
            CredentialSet.tool_instance_id == tool_instance_id,
            CredentialSet.is_active == True,
        ]
        
        if user_id and tenant_id:
            user_stmt = select(CredentialSet).where(
                and_(
                    *conditions,
                    CredentialSet.scope == CredentialScope.USER.value,
                    CredentialSet.user_id == user_id,
                    CredentialSet.tenant_id == tenant_id,
                )
            )
            result = await self.session.execute(user_stmt)
            user_creds = result.scalar_one_or_none()
            if user_creds:
                return user_creds
        
        if tenant_id:
            tenant_stmt = select(CredentialSet).where(
                and_(
                    *conditions,
                    CredentialSet.scope == CredentialScope.TENANT.value,
                    CredentialSet.tenant_id == tenant_id,
                )
            )
            result = await self.session.execute(tenant_stmt)
            return result.scalar_one_or_none()
        
        return None

    async def get_all_for_instance(
        self,
        tool_instance_id: UUID,
    ) -> List[CredentialSet]:
        """Get all credential sets for a tool instance"""
        stmt = select(CredentialSet).where(
            CredentialSet.tool_instance_id == tool_instance_id
        ).order_by(CredentialSet.created_at.desc())
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def exists_for_scope(
        self,
        tool_instance_id: UUID,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """Check if credentials already exist for given scope"""
        conditions = [
            CredentialSet.tool_instance_id == tool_instance_id,
            CredentialSet.scope == scope,
        ]
        
        if tenant_id:
            conditions.append(CredentialSet.tenant_id == tenant_id)
        if user_id:
            conditions.append(CredentialSet.user_id == user_id)
        
        stmt = select(func.count()).where(and_(*conditions))
        count = await self.session.scalar(stmt) or 0
        return count > 0
    
    async def get_default_for_scope(
        self,
        tool_instance_id: UUID,
        scope: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> Optional[CredentialSet]:
        """
        Get default credential set for a specific scope.
        
        If is_default=true exists, returns it.
        If multiple credentials exist but no default, returns None (error case).
        If only one credential exists, returns it.
        """
        conditions = [
            CredentialSet.tool_instance_id == tool_instance_id,
            CredentialSet.scope == scope,
            CredentialSet.is_active == True,
        ]
        
        if scope == "tenant" and tenant_id:
            conditions.append(CredentialSet.tenant_id == tenant_id)
        elif scope == "user" and tenant_id and user_id:
            conditions.append(CredentialSet.tenant_id == tenant_id)
            conditions.append(CredentialSet.user_id == user_id)
        
        # Try to get default first
        default_stmt = select(CredentialSet).where(
            and_(*conditions, CredentialSet.is_default == True)
        )
        result = await self.session.execute(default_stmt)
        default_cred = result.scalar_one_or_none()
        
        if default_cred:
            return default_cred
        
        # If no default, check if only one exists
        all_stmt = select(CredentialSet).where(and_(*conditions))
        result = await self.session.execute(all_stmt)
        all_creds = list(result.scalars().all())
        
        if len(all_creds) == 1:
            return all_creds[0]
        elif len(all_creds) > 1:
            # Multiple credentials but no default - this is an error state
            # Log warning and return None
            from app.core.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(
                f"Multiple credentials found for instance {tool_instance_id} "
                f"scope {scope} but no default set"
            )
            return None
        
        return None
