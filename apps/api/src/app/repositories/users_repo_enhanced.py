from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from datetime import datetime, timezone
import uuid

from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs
from app.repositories._base import BaseRepository, AsyncBaseRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

class UsersRepository(BaseRepository[Users]):
    """Enhanced users repository with comprehensive user management"""
    
    def __init__(self, session: Session):
        super().__init__(session, Users)
    
    def get_by_login(self, login: str) -> Optional[Users]:
        """Get user by login"""
        return self.get_by_field('login', login)
    
    def get_by_email(self, email: str) -> Optional[Users]:
        """Get user by email"""
        return self.get_by_field('email', email)
    
    def get_active_users(self) -> List[Users]:
        """Get all active users"""
        return self.list(filters={'is_active': True})
    
    def get_users_by_role(self, role: str) -> List[Users]:
        """Get users by role"""
        return self.list(filters={'role': role})
    
    def search_users(self, query: str, limit: int = 50) -> List[Users]:
        """Search users by login or email"""
        return self.search(query, ['login', 'email'], limit)
    
    def create_user(self, login: str, password_hash: str, role: str = "reader",
                   email: Optional[str] = None, is_active: bool = True) -> Users:
        """Create a new user with validation"""
        # Check if user already exists
        if self.get_by_login(login):
            raise ValueError(f"User with login '{login}' already exists")
        
        if email and self.get_by_email(email):
            raise ValueError(f"User with email '{email}' already exists")
        
        return self.create(
            login=login,
            password_hash=password_hash,
            role=role,
            email=email,
            is_active=is_active
        )
    
    def update_user_role(self, user_id: str, role: str) -> Optional[Users]:
        """Update user role"""
        return self.update(user_id, role=role)
    
    def deactivate_user(self, user_id: str) -> Optional[Users]:
        """Deactivate user"""
        return self.update(user_id, is_active=False)
    
    def activate_user(self, user_id: str) -> Optional[Users]:
        """Activate user"""
        return self.update(user_id, is_active=True)
    
    def change_password(self, user_id: str, new_password_hash: str) -> Optional[Users]:
        """Change user password"""
        return self.update(user_id, password_hash=new_password_hash)
    
    def list_users_paginated(self, query: Optional[str] = None, role: Optional[str] = None,
                            is_active: Optional[bool] = None, limit: int = 50,
                            cursor: Optional[str] = None) -> Tuple[List[Users], bool, Optional[str]]:
        """List users with pagination and filters"""
        filters = {}
        if role:
            filters['role'] = role
        if is_active is not None:
            filters['is_active'] = is_active
        
        # Apply text search
        if query:
            users = self.search(query, ['login', 'email'], limit + 1)
        else:
            users = self.list(filters=filters, limit=limit + 1)
        
        has_more = len(users) > limit
        if has_more:
            users = users[:-1]
            next_cursor = users[-1].created_at.isoformat() if users else None
        else:
            next_cursor = None
        
        return users, has_more, next_cursor


class UserTokensRepository(BaseRepository[UserTokens]):
    """Repository for user PAT tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, UserTokens)
    
    def get_by_hash(self, token_hash: str) -> Optional[UserTokens]:
        """Get token by hash"""
        return self.get_by_field('token_hash', token_hash)
    
    def get_user_tokens(self, user_id: str, include_revoked: bool = False) -> List[UserTokens]:
        """Get all tokens for a user"""
        filters = {'user_id': user_id}
        if not include_revoked:
            filters['revoked_at'] = None
        return self.list(filters=filters, order_by='-created_at')
    
    def create_token(self, user_id: str, token_hash: str, name: str,
                    scopes: Optional[List[str]] = None, expires_at: Optional[datetime] = None) -> UserTokens:
        """Create a new PAT token"""
        return self.create(
            user_id=user_id,
            token_hash=token_hash,
            name=name,
            scopes=scopes,
            expires_at=expires_at
        )
    
    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token"""
        return self.update(token_id, revoked_at=datetime.now(timezone.utc)) is not None
    
    def is_token_valid(self, token_hash: str) -> bool:
        """Check if token is valid (not revoked and not expired)"""
        token = self.get_by_hash(token_hash)
        if not token:
            return False
        
        if token.revoked_at:
            return False
        
        if token.expires_at and token.expires_at < datetime.now(timezone.utc):
            return False
        
        return True


class UserRefreshTokensRepository(BaseRepository[UserRefreshTokens]):
    """Repository for user refresh tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, UserRefreshTokens)
    
    def get_by_hash(self, refresh_hash: str) -> Optional[UserRefreshTokens]:
        """Get refresh token by hash"""
        return self.get_by_field('refresh_hash', refresh_hash)
    
    def create_refresh_token(self, user_id: str, refresh_hash: str, expires_at: datetime) -> UserRefreshTokens:
        """Create a new refresh token"""
        return self.create(
            user_id=user_id,
            refresh_hash=refresh_hash,
            expires_at=expires_at
        )
    
    def revoke_token(self, refresh_hash: str) -> bool:
        """Revoke a refresh token"""
        return self.update(refresh_hash, revoked=True) is not None
    
    def is_token_valid(self, refresh_hash: str) -> bool:
        """Check if refresh token is valid"""
        token = self.get_by_hash(refresh_hash)
        if not token:
            return False
        
        if token.revoked:
            return False
        
        if token.expires_at < datetime.now(timezone.utc):
            return False
        
        return True


class PasswordResetTokensRepository(BaseRepository[PasswordResetTokens]):
    """Repository for password reset tokens"""
    
    def __init__(self, session: Session):
        super().__init__(session, PasswordResetTokens)
    
    def get_by_hash(self, token_hash: str) -> Optional[PasswordResetTokens]:
        """Get password reset token by hash"""
        token = self.get_by_field('token_hash', token_hash)
        if not token:
            return None
        
        # Check if token is expired or already used
        if token.used_at or token.expires_at < datetime.now(timezone.utc):
            return None
        
        return token
    
    def create_token(self, user_id: str, token_hash: str, expires_at: datetime) -> PasswordResetTokens:
        """Create a password reset token"""
        return self.create(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
    
    def use_token(self, token_hash: str) -> bool:
        """Mark token as used"""
        return self.update(token_hash, used_at=datetime.now(timezone.utc)) is not None


class AuditLogsRepository(BaseRepository[AuditLogs]):
    """Repository for audit logs"""
    
    def __init__(self, session: Session):
        super().__init__(session, AuditLogs)
    
    def create_log(self, actor_user_id: Optional[str], action: str,
                  object_type: Optional[str] = None, object_id: Optional[str] = None,
                  meta: Optional[Dict[str, Any]] = None, ip: Optional[str] = None,
                  user_agent: Optional[str] = None, request_id: Optional[str] = None) -> AuditLogs:
        """Create an audit log entry"""
        return self.create(
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            meta=meta,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id
        )
    
    def get_logs_paginated(self, actor_user_id: Optional[str] = None, action: Optional[str] = None,
                          object_type: Optional[str] = None, limit: int = 50,
                          cursor: Optional[str] = None) -> Tuple[List[AuditLogs], bool, Optional[str]]:
        """Get audit logs with pagination"""
        filters = {}
        if actor_user_id:
            filters['actor_user_id'] = actor_user_id
        if action:
            filters['action'] = action
        if object_type:
            filters['object_type'] = object_type
        
        logs = self.list(filters=filters, order_by='-ts', limit=limit + 1)
        
        has_more = len(logs) > limit
        if has_more:
            logs = logs[:-1]
            next_cursor = logs[-1].ts.isoformat() if logs else None
        else:
            next_cursor = None
        
        return logs, has_more, next_cursor


# Async versions
class AsyncUsersRepository(AsyncBaseRepository[Users]):
    """Async users repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Users)
    
    async def get_by_login(self, login: str) -> Optional[Users]:
        """Get user by login"""
        return await self.get_by_field('login', login)
    
    async def get_by_email(self, email: str) -> Optional[Users]:
        """Get user by email"""
        return await self.get_by_field('email', email)
    
    async def get_active_users(self) -> List[Users]:
        """Get all active users"""
        return await self.list(filters={'is_active': True})
    
    async def create_user(self, login: str, password_hash: str, role: str = "reader",
                         email: Optional[str] = None, is_active: bool = True) -> Users:
        """Create a new user with validation"""
        # Check if user already exists
        if await self.get_by_login(login):
            raise ValueError(f"User with login '{login}' already exists")
        
        if email and await self.get_by_email(email):
            raise ValueError(f"User with email '{email}' already exists")
        
        return await self.create(
            login=login,
            password_hash=password_hash,
            role=role,
            email=email,
            is_active=is_active
        )


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
