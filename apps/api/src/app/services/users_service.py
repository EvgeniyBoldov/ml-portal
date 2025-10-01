"""
Enhanced users service with comprehensive business logic
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
import hashlib
import secrets
import bcrypt

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services._base import BaseService, AsyncBaseService, RepositoryService, AsyncRepositoryService
from app.repositories.users_repo import (
    UsersRepository, UserTokensRepository, UserRefreshTokensRepository,
    PasswordResetTokensRepository, AuditLogsRepository,
    create_users_repository, create_user_tokens_repository,
    create_user_refresh_tokens_repository, create_password_reset_tokens_repository,
    create_audit_logs_repository, create_async_users_repository
)
from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs
from app.core.logging import get_logger

logger = get_logger(__name__)

class UsersService(RepositoryService[Users]):
    """Enhanced users service with comprehensive business logic"""
    
    def __init__(self, session: Session):
        self.users_repo = create_users_repository(session)
        self.tokens_repo = create_user_tokens_repository(session)
        self.refresh_tokens_repo = create_user_refresh_tokens_repository(session)
        self.password_reset_repo = create_password_reset_tokens_repository(session)
        self.audit_repo = create_audit_logs_repository(session)
        super().__init__(session, self.users_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for user creation"""
        return ["login", "password_hash"]
    
    def _process_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process user creation data"""
        processed = data.copy()
        
        # Sanitize login
        if "login" in processed:
            processed["login"] = self._sanitize_string(processed["login"], 100).lower()
        
        # Sanitize email
        if "email" in processed and processed["email"]:
            processed["email"] = self._sanitize_string(processed["email"], 255).lower()
            if not self._validate_email(processed["email"]):
                raise ValueError("Invalid email format")
        
        # Set default values
        processed.setdefault("role", "reader")
        processed.setdefault("is_active", True)
        processed.setdefault("created_at", self._get_current_time())
        processed.setdefault("updated_at", self._get_current_time())
        
        return processed
    
    def _process_update_data(self, data: Dict[str, Any], existing_entity: Users) -> Dict[str, Any]:
        """Process user update data"""
        processed = data.copy()
        
        # Sanitize email if provided
        if "email" in processed and processed["email"]:
            processed["email"] = self._sanitize_string(processed["email"], 255).lower()
            if not self._validate_email(processed["email"]):
                raise ValueError("Invalid email format")
        
        # Update timestamp
        processed["updated_at"] = self._get_current_time()
        
        return processed
    
    def _can_delete(self, entity: Users) -> bool:
        """Check if user can be deleted"""
        # Check if user has active tokens
        active_tokens = self.tokens_repo.get_user_tokens(str(entity.id), include_revoked=False)
        if active_tokens:
            return False
        
        # Check if user has active refresh tokens
        # This would require a method to check active refresh tokens
        return True
    
    def create_user(self, login: str, password: str, role: str = "reader",
                   email: Optional[str] = None, is_active: bool = True) -> Users:
        """Create a new user with password hashing"""
        try:
            # Validate inputs
            if not login or len(login.strip()) < 3:
                raise ValueError("Login must be at least 3 characters long")
            
            if not password or len(password) < 8:
                raise ValueError("Password must be at least 8 characters long")
            
            if email and not self._validate_email(email):
                raise ValueError("Invalid email format")
            
            # Check if user already exists
            if self.users_repo.get_by_login(login):
                raise ValueError("User with this login already exists")
            
            if email and self.users_repo.get_by_email(email):
                raise ValueError("User with this email already exists")
            
            # Hash password
            password_hash = self._hash_password(password)
            
            # Create user
            user = self.users_repo.create_user(
                login=login,
                password_hash=password_hash,
                role=role,
                email=email,
                is_active=is_active
            )
            
            # Log audit
            self.audit_repo.create_log(
                actor_user_id=None,  # System action
                action="user_created",
                object_type="user",
                object_id=str(user.id),
                meta={"login": login, "role": role, "email": email}
            )
            
            self._log_operation("create_user", str(user.id), {"login": login, "role": role})
            return user
            
        except Exception as e:
            self._handle_error("create_user", e, {"login": login, "email": email})
            raise
    
    def authenticate_user(self, login: str, password: str) -> Optional[Users]:
        """Authenticate user with login and password"""
        try:
            user = self.users_repo.get_by_login(login)
            if not user:
                return None
            
            if not user.is_active:
                return None
            
            if not self._verify_password(password, user.password_hash):
                return None
            
            # Log successful authentication
            self.audit_repo.create_log(
                actor_user_id=str(user.id),
                action="user_authenticated",
                object_type="auth",
                object_id=str(user.id),
                meta={"login": login}
            )
            
            return user
            
        except Exception as e:
            self._handle_error("authenticate_user", e, {"login": login})
            raise
    
    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Change user password with old password verification"""
        try:
            user = self.users_repo.get_by_id(user_id)
            if not user:
                raise ValueError("User not found")
            
            if not self._verify_password(old_password, user.password_hash):
                raise ValueError("Invalid current password")
            
            if len(new_password) < 8:
                raise ValueError("New password must be at least 8 characters long")
            
            new_password_hash = self._hash_password(new_password)
            self.users_repo.change_password(user_id, new_password_hash)
            
            # Log password change
            self.audit_repo.create_log(
                actor_user_id=user_id,
                action="password_changed",
                object_type="user",
                object_id=user_id
            )
            
            self._log_operation("change_password", user_id)
            return True
            
        except Exception as e:
            self._handle_error("change_password", e, {"user_id": user_id})
            raise
    
    def reset_password_request(self, email: str) -> bool:
        """Request password reset"""
        try:
            user = self.users_repo.get_by_email(email)
            if not user:
                # Don't reveal if email exists
                return True
            
            # Generate reset token
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires_at = self._get_current_time() + timedelta(hours=24)
            
            # Create reset token
            self.password_reset_repo.create_token(
                user_id=str(user.id),
                token_hash=token_hash,
                expires_at=expires_at
            )
            
            # Log reset request
            self.audit_repo.create_log(
                actor_user_id=str(user.id),
                action="password_reset_requested",
                object_type="user",
                object_id=str(user.id),
                meta={"email": email}
            )
            
            # TODO: Send email with reset token
            # For now, just log the token (in production, send via email)
            logger.info(f"Password reset token for {email}: {token}")
            
            return True
            
        except Exception as e:
            self._handle_error("reset_password_request", e, {"email": email})
            raise
    
    def reset_password_confirm(self, token: str, new_password: str) -> bool:
        """Confirm password reset with token"""
        try:
            if len(new_password) < 8:
                raise ValueError("Password must be at least 8 characters long")
            
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            reset_token = self.password_reset_repo.get_by_hash(token_hash)
            
            if not reset_token:
                raise ValueError("Invalid or expired reset token")
            
            # Update password
            new_password_hash = self._hash_password(new_password)
            self.users_repo.change_password(str(reset_token.user_id), new_password_hash)
            
            # Mark token as used
            self.password_reset_repo.use_token(token_hash)
            
            # Log password reset
            self.audit_repo.create_log(
                actor_user_id=str(reset_token.user_id),
                action="password_reset_completed",
                object_type="user",
                object_id=str(reset_token.user_id)
            )
            
            return True
            
        except Exception as e:
            self._handle_error("reset_password_confirm", e, {"token": token[:10] + "..."})
            raise
    
    def create_pat_token(self, user_id: str, name: str, scopes: Optional[List[str]] = None,
                        expires_at: Optional[datetime] = None) -> Tuple[UserTokens, str]:
        """Create a Personal Access Token"""
        try:
            # Generate token
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Create token record
            token_record = self.tokens_repo.create_token(
                user_id=user_id,
                token_hash=token_hash,
                name=name,
                scopes=scopes,
                expires_at=expires_at
            )
            
            # Log token creation
            self.audit_repo.create_log(
                actor_user_id=user_id,
                action="pat_token_created",
                object_type="token",
                object_id=str(token_record.id),
                meta={"name": name, "scopes": scopes}
            )
            
            self._log_operation("create_pat_token", str(token_record.id), {"user_id": user_id, "name": name})
            return token_record, token
            
        except Exception as e:
            self._handle_error("create_pat_token", e, {"user_id": user_id, "name": name})
            raise
    
    def revoke_pat_token(self, user_id: str, token_id: str) -> bool:
        """Revoke a Personal Access Token"""
        try:
            # Get token to verify ownership
            token = self.tokens_repo.get_by_id(token_id)
            if not token or str(token.user_id) != user_id:
                return False
            
            # Revoke token
            result = self.tokens_repo.revoke_token(token_id)
            
            if result:
                # Log token revocation
                self.audit_repo.create_log(
                    actor_user_id=user_id,
                    action="pat_token_revoked",
                    object_type="token",
                    object_id=token_id
                )
            
            return result
            
        except Exception as e:
            self._handle_error("revoke_pat_token", e, {"user_id": user_id, "token_id": token_id})
            raise
    
    def get_user_tokens(self, user_id: str, include_revoked: bool = False) -> List[UserTokens]:
        """Get user's PAT tokens"""
        try:
            tokens = self.tokens_repo.get_user_tokens(user_id, include_revoked)
            self._log_operation("get_user_tokens", user_id, {"count": len(tokens)})
            return tokens
        except Exception as e:
            self._handle_error("get_user_tokens", e, {"user_id": user_id})
            raise
    
    def search_users(self, query: str, role: Optional[str] = None, 
                    is_active: Optional[bool] = None, limit: int = 50) -> List[Users]:
        """Search users with filters"""
        try:
            if query:
                users = self.users_repo.search_users(query, limit)
            else:
                filters = {}
                if role:
                    filters["role"] = role
                if is_active is not None:
                    filters["is_active"] = is_active
                users = self.users_repo.list(filters=filters, limit=limit)
            
            self._log_operation("search_users", "multiple", {
                "query": query,
                "role": role,
                "count": len(users)
            })
            return users
            
        except Exception as e:
            self._handle_error("search_users", e, {"query": query, "role": role})
            raise
    
    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics"""
        try:
            user = self.users_repo.get_by_id(user_id)
            if not user:
                raise ValueError("User not found")
            
            # Get token count
            tokens = self.tokens_repo.get_user_tokens(user_id, include_revoked=False)
            active_tokens = len(tokens)
            
            # Get audit log count (last 30 days)
            thirty_days_ago = self._get_current_time() - timedelta(days=30)
            # This would require a method to count audit logs by user and date range
            
            stats = {
                "user_id": user_id,
                "login": user.login,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "active_tokens": active_tokens,
                "total_tokens": len(self.tokens_repo.get_user_tokens(user_id, include_revoked=True))
            }
            
            return stats
            
        except Exception as e:
            self._handle_error("get_user_stats", e, {"user_id": user_id})
            raise
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


class AsyncUsersService(AsyncRepositoryService[Users]):
    """Async users service"""
    
    def __init__(self, session: AsyncSession):
        self.users_repo = create_async_users_repository(session)
        super().__init__(session, self.users_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for user creation"""
        return ["login", "password_hash"]
    
    async def create_user(self, login: str, password: str, role: str = "reader",
                         email: Optional[str] = None, is_active: bool = True) -> Users:
        """Create a new user with password hashing"""
        try:
            if not login or len(login.strip()) < 3:
                raise ValueError("Login must be at least 3 characters long")
            
            if not password or len(password) < 8:
                raise ValueError("Password must be at least 8 characters long")
            
            if email and not self._validate_email(email):
                raise ValueError("Invalid email format")
            
            # Check if user already exists
            if await self.users_repo.get_by_login(login):
                raise ValueError("User with this login already exists")
            
            if email and await self.users_repo.get_by_email(email):
                raise ValueError("User with this email already exists")
            
            # Hash password
            password_hash = self._hash_password(password)
            
            # Create user
            user = await self.users_repo.create_user(
                login=login,
                password_hash=password_hash,
                role=role,
                email=email,
                is_active=is_active
            )
            
            self._log_operation("create_user", str(user.id), {"login": login, "role": role})
            return user
            
        except Exception as e:
            self._handle_error("create_user", e, {"login": login, "email": email})
            raise
    
    async def authenticate_user(self, login: str, password: str) -> Optional[Users]:
        """Authenticate user with login and password"""
        try:
            user = await self.users_repo.get_by_login(login)
            if not user or not user.is_active:
                return None
            
            if not self._verify_password(password, user.password_hash):
                return None
            
            return user
            
        except Exception as e:
            self._handle_error("authenticate_user", e, {"login": login})
            raise
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# Factory functions
def create_users_service(session: Session) -> UsersService:
    """Create users service"""
    return UsersService(session)

def create_async_users_service(session: AsyncSession) -> AsyncUsersService:
    """Create async users service"""
    return AsyncUsersService(session)
