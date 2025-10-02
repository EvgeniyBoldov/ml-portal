from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, tuple_
from datetime import datetime, timezone
import uuid
import base64
import json

from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs
from app.models.tenant import UserTenants, Tenants
from app.repositories.base import Repository, AsyncRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class UsersRepository(Repository[Users]):
    """Users repository without tenant isolation - handles M2M tenant relationships"""
    
    def __init__(self, session: Session):
        super().__init__(session, Users)
    
    def add_to_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID, is_default: bool = False) -> UserTenants:
        """Add user to tenant"""
        # If setting as default, unset other defaults for this user
        if is_default:
            existing_defaults = self.session.execute(
                select(UserTenants).where(
                    and_(
                        UserTenants.user_id == user_id,
                        UserTenants.is_default == True
                    )
                )
            ).scalars().all()
            for ut in existing_defaults:
                ut.is_default = False
        
        # Create new user-tenant link
        user_tenant = UserTenants(
            user_id=user_id,
            tenant_id=tenant_id,
            is_default=is_default
        )
        self.session.add(user_tenant)
        self.session.flush()
        return user_tenant
    
    def set_default_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Set default tenant for user (unset others)"""
        # Unset all current defaults
        self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.is_default == True
                )
            )
        ).scalars().all()
        for ut in self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.is_default == True
                )
            )
        ).scalars().all():
            ut.is_default = False
        
        # Set new default
        user_tenant = self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        
        if user_tenant:
            user_tenant.is_default = True
        else:
            # Create link if it doesn't exist
            self.add_to_tenant(user_id, tenant_id, is_default=True)
    
    def get_default_tenant(self, user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get default tenant for user"""
        user_tenant = self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.is_default == True
                )
            )
        ).scalar_one_or_none()
        
        return user_tenant.tenant_id if user_tenant else None
    
    def list_by_tenant(self, tenant_id: uuid.UUID, *, limit: int = 50, cursor: Optional[str] = None) -> Tuple[List[Users], Optional[str]]:
        """List users by tenant with seek-based pagination"""
        # Validate limit
        if not (1 <= limit <= 100):
            raise ValueError("limit_out_of_range")
        
        # Build query with join to user_tenants
        query = (
            select(Users)
            .join(UserTenants, Users.id == UserTenants.user_id)
            .where(UserTenants.tenant_id == tenant_id)
            .order_by(desc(Users.created_at), desc(Users.id))
            .limit(limit + 1)  # Get one extra to determine if there's a next page
        )
        
        # Apply cursor filter if provided
        if cursor:
            try:
                cursor_data = self._decode_cursor(cursor)
                query = query.where(
                    tuple_(Users.created_at, Users.id) < (cursor_data["created_at"], cursor_data["id"])
                )
            except Exception:
                raise ValueError("invalid_cursor")
        
        # Execute query
        results = self.session.execute(query).scalars().all()
        
        # Determine pagination
        has_next = len(results) > limit
        if has_next:
            results = results[:limit]  # Remove the extra item
        
        # Generate next cursor
        next_cursor = None
        if has_next and results:
            last_user = results[-1]
            next_cursor = self._encode_cursor({
                "created_at": last_user.created_at.isoformat(),
                "id": str(last_user.id)
            })
        
        return results, next_cursor
    
    def _encode_cursor(self, data: Dict[str, Any]) -> str:
        """Encode cursor data to base64 JSON string"""
        json_str = json.dumps(data)
        return base64.b64encode(json_str.encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        """Decode cursor from base64 JSON string"""
        try:
            json_str = base64.b64decode(cursor.encode()).decode()
            data = json.loads(json_str)
            
            # Validate required fields
            if "id" not in data or "created_at" not in data:
                raise ValueError("invalid_cursor")
            
            # Convert string UUID back to UUID object
            data["id"] = uuid.UUID(data["id"])
            
            # Convert ISO string back to datetime
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
            
            return data
        except Exception as e:
            raise ValueError("invalid_cursor") from e
    
    def is_user_in_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Check if user belongs to tenant"""
        result = self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        
        return result is not None
    
    def get_user_tenants(self, user_id: uuid.UUID) -> List[Tenants]:
        """Get all tenants for a user"""
        result = self.session.execute(
            select(Tenants)
            .join(UserTenants, Tenants.id == UserTenants.tenant_id)
            .where(UserTenants.user_id == user_id)
        ).scalars().all()
        
        return result
    
    def remove_from_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Remove user from tenant"""
        user_tenant = self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        
        if user_tenant:
            self.session.delete(user_tenant)
            return True
        return False


class UserTokensRepository(Repository[UserTokens]):
    """Repository for user tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, UserTokens)


class UserRefreshTokensRepository(Repository[UserRefreshTokens]):
    """Repository for user refresh tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, UserRefreshTokens)


class PasswordResetTokensRepository(Repository[PasswordResetTokens]):
    """Repository for password reset tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, PasswordResetTokens)


class AuditLogsRepository(Repository[AuditLogs]):
    """Repository for audit logs"""
    
    def __init__(self, session: Session):
        super().__init__(session, AuditLogs)


class AsyncUsersRepository(AsyncRepository[Users]):
    """Async users repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Users)
    
    async def add_to_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID, is_default: bool = False) -> UserTenants:
        """Add user to tenant"""
        # If setting as default, unset other defaults for this user
        if is_default:
            existing_defaults = await self.session.execute(
                select(UserTenants).where(
                    and_(
                        UserTenants.user_id == user_id,
                        UserTenants.is_default == True
                    )
                )
            )
            for ut in existing_defaults.scalars().all():
                ut.is_default = False
        
        # Create new user-tenant link
        user_tenant = UserTenants(
            user_id=user_id,
            tenant_id=tenant_id,
            is_default=is_default
        )
        self.session.add(user_tenant)
        await self.session.flush()
        return user_tenant
    
    async def set_default_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Set default tenant for user (unset others)"""
        # Unset all current defaults
        existing_defaults = await self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.is_default == True
                )
            )
        )
        for ut in existing_defaults.scalars().all():
            ut.is_default = False
        
        # Set new default
        user_tenant_result = await self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        )
        user_tenant = user_tenant_result.scalar_one_or_none()
        
        if user_tenant:
            user_tenant.is_default = True
        else:
            # Create link if it doesn't exist
            await self.add_to_tenant(user_id, tenant_id, is_default=True)
    
    async def get_default_tenant(self, user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get default tenant for user"""
        result = await self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.is_default == True
                )
            )
        )
        user_tenant = result.scalar_one_or_none()
        
        return user_tenant.tenant_id if user_tenant else None
    
    async def list_by_tenant(self, tenant_id: uuid.UUID, *, limit: int = 50, cursor: Optional[str] = None) -> Tuple[List[Users], Optional[str]]:
        """List users by tenant with seek-based pagination"""
        # Validate limit
        if not (1 <= limit <= 100):
            raise ValueError("limit_out_of_range")
        
        # Build query with join to user_tenants
        query = (
            select(Users)
            .join(UserTenants, Users.id == UserTenants.user_id)
            .where(UserTenants.tenant_id == tenant_id)
            .order_by(desc(Users.created_at), desc(Users.id))
            .limit(limit + 1)  # Get one extra to determine if there's a next page
        )
        
        # Apply cursor filter if provided
        if cursor:
            try:
                cursor_data = self._decode_cursor(cursor)
                query = query.where(
                    tuple_(Users.created_at, Users.id) < (cursor_data["created_at"], cursor_data["id"])
                )
            except Exception:
                raise ValueError("invalid_cursor")
        
        # Execute query
        result = await self.session.execute(query)
        results = result.scalars().all()
        
        # Determine pagination
        has_next = len(results) > limit
        if has_next:
            results = results[:limit]  # Remove the extra item
        
        # Generate next cursor
        next_cursor = None
        if has_next and results:
            last_user = results[-1]
            next_cursor = self._encode_cursor({
                "created_at": last_user.created_at.isoformat(),
                "id": str(last_user.id)
            })
        
        return results, next_cursor
    
    async def is_user_in_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Check if user belongs to tenant"""
        result = await self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        )
        
        return result.scalar_one_or_none() is not None
    
    async def get_user_tenants(self, user_id: uuid.UUID) -> List[Tenants]:
        """Get all tenants for a user"""
        result = await self.session.execute(
            select(Tenants)
            .join(UserTenants, Tenants.id == UserTenants.tenant_id)
            .where(UserTenants.user_id == user_id)
        )
        
        return result.scalars().all()
    
    async def remove_from_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Remove user from tenant"""
        result = await self.session.execute(
            select(UserTenants).where(
                and_(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
                )
            )
        )
        user_tenant = result.scalar_one_or_none()
        
        if user_tenant:
            await self.session.delete(user_tenant)
            return True
        return False
    
    def _encode_cursor(self, data: Dict[str, Any]) -> str:
        """Encode cursor data to base64 JSON string"""
        json_str = json.dumps(data)
        return base64.b64encode(json_str.encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        """Decode cursor from base64 JSON string"""
        try:
            json_str = base64.b64decode(cursor.encode()).decode()
            data = json.loads(json_str)
            
            # Validate required fields
            if "id" not in data or "created_at" not in data:
                raise ValueError("invalid_cursor")
            
            # Convert string UUID back to UUID object
            data["id"] = uuid.UUID(data["id"])
            
            # Convert ISO string back to datetime
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
            
            return data
        except Exception as e:
            raise ValueError("invalid_cursor") from e


# Factory functions for easy instantiation
def create_users_repository(session: Session) -> UsersRepository:
    """Create users repository"""
    return UsersRepository(session)

def create_user_tokens_repository(session: Session) -> UserTokensRepository:
    """Create user tokens repository"""
    return UserTokensRepository(session)

def create_user_refresh_tokens_repository(session: Session) -> UserRefreshTokensRepository:
    """Create user refresh tokens repository"""
    return UserRefreshTokensRepository(session)

def create_password_reset_tokens_repository(session: Session) -> PasswordResetTokensRepository:
    """Create password reset tokens repository"""
    return PasswordResetTokensRepository(session)

def create_audit_logs_repository(session: Session) -> AuditLogsRepository:
    """Create audit logs repository"""
    return AuditLogsRepository(session)

def create_async_users_repository(session: AsyncSession) -> AsyncUsersRepository:
    """Create async users repository"""
    return AsyncUsersRepository(session)