"""
PermissionSet model - набор разрешений для tools и collections
"""
import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import String, DateTime, ForeignKey, func, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PermissionScope(str, Enum):
    """Scope уровень для PermissionSet"""
    DEFAULT = "default"
    TENANT = "tenant"
    USER = "user"


class PermissionSet(Base):
    """
    Набор разрешений для tools и collections.
    
    Иерархия наследования: default → tenant → user
    Приоритет при резолве: user > tenant > default
    
    Логика резолва:
    1. Проверяем user level - если есть явное разрешение/запрет, используем его
    2. Если на user level не указано - проверяем tenant level
    3. Если на tenant level не указано - проверяем default level
    4. Если нигде не указано - запрещено по умолчанию
    
    Deny всегда побеждает allow на том же уровне.
    """
    __tablename__ = "permission_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    allowed_tools: Mapped[List[str]] = mapped_column(JSONB, default=list)
    denied_tools: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    allowed_collections: Mapped[List[str]] = mapped_column(JSONB, default=list)
    denied_collections: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name="permission_sets_scope_check"
        ),
        CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name="permission_sets_scope_refs_check"
        ),
        UniqueConstraint('scope', 'tenant_id', 'user_id', name='uix_permission_sets_scope'),
    )

    def __repr__(self) -> str:
        return f"<PermissionSet {self.scope} tenant={self.tenant_id} user={self.user_id}>"
