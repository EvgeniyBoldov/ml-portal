from __future__ import annotations
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, desc
from datetime import datetime, timezone
import uuid

from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs

class UsersRepoSync:
    def __init__(self, session: Session):
        self.s = session

    def by_login(self, login: str) -> Optional[Users]:
        result = self.s.execute(select(Users).where(Users.login == login))
        return result.scalar_one_or_none()

    def by_email(self, email: str) -> Optional[Users]:
        """Find user by email address."""
        result = self.s.execute(select(Users).where(Users.email == email))
        return result.scalar_one_or_none()

    def get(self, user_id):
        return self.s.get(Users, user_id)

    # Refresh tokens
    def add_refresh(self, rec: UserRefreshTokens) -> None:
        self.s.add(rec)

    def get_refresh_by_hash(self, refresh_hash: str) -> Optional[UserRefreshTokens]:
        result = self.s.execute(select(UserRefreshTokens).where(UserRefreshTokens.refresh_hash == refresh_hash))
        return result.scalar_one_or_none()

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
        self.s.flush()
        self.s.refresh(user)
        return user

    def create(self, login: str, password_hash: str, role: str = "reader",
              email: Optional[str] = None, is_active: bool = True) -> Users:
        """Alias for create_user for backward compatibility."""
        return self.create_user(login, password_hash, role, email, is_active)

    def update_user(self, user_id: str, **updates) -> Optional[Users]:
        """Update user fields."""
        user = self.get(user_id)
        if not user:
            return None

        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.now(timezone.utc)
        self.s.flush()
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

        result = self.s.execute(stmt)
        users = result.scalars().all()
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

        result = self.s.execute(stmt)
        return result.scalar() or 0

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
        return token

    def get_user_tokens(self, user_id: str, include_revoked: bool = False) -> List[UserTokens]:
        """Get all PAT tokens for a user."""
        stmt = select(UserTokens).where(UserTokens.user_id == user_id)
        if not include_revoked:
            stmt = stmt.where(UserTokens.revoked_at.is_(None))

        result = self.s.execute(stmt)
        return result.scalars().all()

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a PAT token."""
        token = self.s.get(UserTokens, token_id)
        if token and not token.revoked_at:
            token.revoked_at = datetime.now(timezone.utc)
            return True
        return False

    def get_token_by_hash(self, token_hash: str) -> Optional[UserTokens]:
        """Get token by hash."""
        result = self.s.execute(select(UserTokens).where(UserTokens.token_hash == token_hash))
        return result.scalar_one_or_none()

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
        return token

    def get_password_reset_token(self, token_hash: str) -> Optional[PasswordResetTokens]:
        """Get password reset token by hash."""
        result = self.s.execute(
            select(PasswordResetTokens)
            .where(PasswordResetTokens.token_hash == token_hash)
            .where(PasswordResetTokens.used_at.is_(None))
            .where(PasswordResetTokens.expires_at > datetime.now(timezone.utc))
        )
        return result.scalar_one_or_none()

    def use_password_reset_token(self, token_hash: str) -> bool:
        """Mark password reset token as used."""
        token = self.get_password_reset_token(token_hash)
        if token:
            token.used_at = datetime.now(timezone.utc)
            return True
        return False

    # Audit log methods
    def get_audit_logs(self, actor_user_id: Optional[str] = None, action: Optional[str] = None,
                      object_type: Optional[str] = None, limit: int = 100,
                      cursor: Optional[str] = None) -> tuple[List[AuditLogs], bool, Optional[str]]:
        """Get audit logs with pagination and filters."""
        stmt = select(AuditLogs)

        # Apply filters
        if actor_user_id:
            stmt = stmt.where(AuditLogs.actor_user_id == actor_user_id)
        if action:
            stmt = stmt.where(AuditLogs.action == action)
        if object_type:
            stmt = stmt.where(AuditLogs.object_type == object_type)

        # Apply cursor-based pagination
        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor)
                stmt = stmt.where(AuditLogs.ts < cursor_time)
            except ValueError:
                pass  # Invalid cursor, ignore

        # Order and limit
        stmt = stmt.order_by(desc(AuditLogs.ts)).limit(limit + 1)

        result = self.s.execute(stmt)
        logs = result.scalars().all()
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

        result = self.s.execute(stmt)
        return result.scalar() or 0

    def create_audit_log(self, actor_user_id: Optional[str], action: str,
                        object_type: Optional[str] = None, object_id: Optional[str] = None,
                        meta: Optional[Dict[str, Any]] = None, ip: Optional[str] = None,
                        user_agent: Optional[str] = None, request_id: Optional[str] = None) -> AuditLogs:
        """Create an audit log entry."""
        log = AuditLogs(
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            meta=meta,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id
        )
        self.s.add(log)
        return log
