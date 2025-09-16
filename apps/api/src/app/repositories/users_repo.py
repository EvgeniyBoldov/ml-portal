from __future__ import annotations
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, desc
from datetime import datetime
import uuid

from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs

class UsersRepo:
    def __init__(self, session: Session):
        self.s = session

    def by_login(self, login: str) -> Optional[Users]:
        return self.s.execute(select(Users).where(Users.login == login)).scalars().first()

    def get(self, user_id):
        return self.s.get(Users, user_id)

    # Refresh tokens
    def add_refresh(self, rec: UserRefreshTokens) -> None:
        self.s.add(rec)

    def get_refresh_by_hash(self, refresh_hash: str) -> Optional[UserRefreshTokens]:
        return self.s.execute(select(UserRefreshTokens).where(UserRefreshTokens.refresh_hash == refresh_hash)).scalars().first()

    def revoke_refresh(self, refresh_hash: str) -> bool:
        rec = self.get_refresh_by_hash(refresh_hash)
        if rec and not rec.revoked:
            rec.revoked = True
            return True
        return False

    # User management methods
    def create_user(self, login: str, password_hash: str, role: str = "reader", 
                   email: Optional[str] = None, is_active: bool = True) -> Users:
        """Create a new user."""
        user = Users(
            login=login,
            password_hash=password_hash,
            role=role,
            email=email,
            is_active=is_active
        )
        self.s.add(user)
        self.s.commit()
        self.s.refresh(user)
        return user

    def update_user(self, user_id: str, **updates) -> Optional[Users]:
        """Update user fields."""
        user = self.get(user_id)
        if not user:
            return None
        
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        user.updated_at = datetime.utcnow()
        self.s.commit()
        self.s.refresh(user)
        return user

    def list_users(self, query: Optional[str] = None, role: Optional[str] = None, 
                  is_active: Optional[bool] = None, limit: int = 50, 
                  cursor: Optional[str] = None) -> tuple[List[Users], bool, Optional[str]]:
        """List users with pagination and filters."""
        stmt = select(Users)
        
        # Apply filters
        if query:
            stmt = stmt.where(
                or_(
                    Users.login.ilike(f"%{query}%"),
                    Users.email.ilike(f"%{query}%")
                )
            )
        
        if role:
            stmt = stmt.where(Users.role == role)
        
        if is_active is not None:
            stmt = stmt.where(Users.is_active == is_active)
        
        # Apply cursor-based pagination
        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor)
                stmt = stmt.where(Users.created_at < cursor_time)
            except ValueError:
                pass  # Invalid cursor, ignore
        
        # Order and limit
        stmt = stmt.order_by(desc(Users.created_at)).limit(limit + 1)
        
        users = self.s.execute(stmt).scalars().all()
        has_more = len(users) > limit
        
        if has_more:
            users = users[:-1]
            next_cursor = users[-1].created_at.isoformat() if users else None
        else:
            next_cursor = None
        
        return users, has_more, next_cursor

    def count_users(self, query: Optional[str] = None, role: Optional[str] = None, 
                   is_active: Optional[bool] = None) -> int:
        """Count users matching filters."""
        stmt = select(func.count(Users.id))
        
        if query:
            stmt = stmt.where(
                or_(
                    Users.login.ilike(f"%{query}%"),
                    Users.email.ilike(f"%{query}%")
                )
            )
        
        if role:
            stmt = stmt.where(Users.role == role)
        
        if is_active is not None:
            stmt = stmt.where(Users.is_active == is_active)
        
        return self.s.execute(stmt).scalar() or 0

    # PAT Token methods
    def create_token(self, user_id: str, token_hash: str, name: str,
                    scopes: Optional[List[str]] = None, expires_at: Optional[datetime] = None) -> UserTokens:
        """Create a new PAT token."""
        token = UserTokens(
            user_id=user_id,
            token_hash=token_hash,
            name=name,
            scopes=scopes,
            expires_at=expires_at
        )
        self.s.add(token)
        self.s.commit()
        self.s.refresh(token)
        return token

    def get_user_tokens(self, user_id: str, include_revoked: bool = False) -> List[UserTokens]:
        """Get user's PAT tokens."""
        stmt = select(UserTokens).where(UserTokens.user_id == user_id)
        
        if not include_revoked:
            stmt = stmt.where(UserTokens.revoked_at.is_(None))
        
        return self.s.execute(stmt.order_by(desc(UserTokens.created_at))).scalars().all()

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a PAT token."""
        token = self.s.get(UserTokens, token_id)
        if token and not token.revoked_at:
            token.revoked_at = datetime.utcnow()
            self.s.commit()
            return True
        return False

    def get_token_by_hash(self, token_hash: str) -> Optional[UserTokens]:
        """Get token by hash."""
        return self.s.execute(
            select(UserTokens).where(UserTokens.token_hash == token_hash)
        ).scalars().first()

    # Password reset methods
    def create_password_reset_token(self, user_id: str, token_hash: str, 
                                   expires_at: datetime) -> PasswordResetTokens:
        """Create a password reset token."""
        token = PasswordResetTokens(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        self.s.add(token)
        self.s.commit()
        self.s.refresh(token)
        return token

    def get_password_reset_token(self, token_hash: str) -> Optional[PasswordResetTokens]:
        """Get password reset token by hash."""
        return self.s.execute(
            select(PasswordResetTokens)
            .where(
                and_(
                    PasswordResetTokens.token_hash == token_hash,
                    PasswordResetTokens.used_at.is_(None),
                    PasswordResetTokens.expires_at > datetime.utcnow()
                )
            )
        ).scalars().first()

    def use_password_reset_token(self, token_hash: str) -> bool:
        """Mark password reset token as used."""
        token = self.get_password_reset_token(token_hash)
        if token:
            token.used_at = datetime.utcnow()
            self.s.commit()
            return True
        return False

    # Audit log methods
    def get_audit_logs(self, actor_user_id: Optional[str] = None, action: Optional[str] = None,
                      object_type: Optional[str] = None, limit: int = 50,
                      cursor: Optional[str] = None) -> tuple[List[AuditLogs], bool, Optional[str]]:
        """Get audit logs with pagination."""
        stmt = select(AuditLogs)
        
        if actor_user_id:
            stmt = stmt.where(AuditLogs.actor_user_id == actor_user_id)
        
        if action:
            stmt = stmt.where(AuditLogs.action == action)
        
        if object_type:
            stmt = stmt.where(AuditLogs.object_type == object_type)
        
        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor)
                stmt = stmt.where(AuditLogs.ts < cursor_time)
            except ValueError:
                pass
        
        stmt = stmt.order_by(desc(AuditLogs.ts)).limit(limit + 1)
        
        logs = self.s.execute(stmt).scalars().all()
        has_more = len(logs) > limit
        
        if has_more:
            logs = logs[:-1]
            next_cursor = logs[-1].ts.isoformat() if logs else None
        else:
            next_cursor = None
        
        return logs, has_more, next_cursor

    def count_audit_logs(self, actor_user_id: Optional[str] = None, action: Optional[str] = None,
                        object_type: Optional[str] = None) -> int:
        """Count audit logs matching filters."""
        stmt = select(func.count(AuditLogs.id))
        
        if actor_user_id:
            stmt = stmt.where(AuditLogs.actor_user_id == actor_user_id)
        
        if action:
            stmt = stmt.where(AuditLogs.action == action)
        
        if object_type:
            stmt = stmt.where(AuditLogs.object_type == object_type)
        
        return self.s.execute(stmt).scalar() or 0
