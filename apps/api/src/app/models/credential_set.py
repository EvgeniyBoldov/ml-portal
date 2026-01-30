"""
CredentialSet model - набор секретов для авторизации ToolInstance
"""
import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthType(str, Enum):
    """Тип авторизации"""
    TOKEN = "token"
    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "api_key"


class CredentialScope(str, Enum):
    """Scope уровень для CredentialSet"""
    DEFAULT = "default"  # Admin-level credentials
    TENANT = "tenant"
    USER = "user"


class CredentialSet(Base):
    """
    Набор секретов для авторизации в ToolInstance.
    
    Credentials хранятся в зашифрованном виде (encrypted_payload).
    Мастер-ключ для шифрования берется из переменных окружения.
    
    Scope определяет владельца credentials:
    - default: админские креды (глобальные)
    - tenant: общие креды для всего тенанта
    - user: персональные креды пользователя
    
    Приоритет при резолве: user > tenant > default
    """
    __tablename__ = "credential_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    tool_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name="credential_sets_scope_check"
        ),
        CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name="credential_sets_scope_refs_check"
        ),
        CheckConstraint(
            "auth_type IN ('token', 'basic', 'oauth', 'api_key')",
            name="credential_sets_auth_type_check"
        ),
    )

    def __repr__(self) -> str:
        return f"<CredentialSet {self.id} ({self.scope}/{self.auth_type})>"
