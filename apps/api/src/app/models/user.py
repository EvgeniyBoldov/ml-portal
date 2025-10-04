from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from .base import Base

class Users(Base):
    __tablename__ = "users"
    
    # Основные поля
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Роли и права доступа
    role: Mapped[str] = mapped_column(
        String(20), 
        default="reader",
        comment="Role: reader, editor, admin"
    )

    # Флажки доступа (только для editor/admin)
    can_edit_local_docs: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        comment="Can edit local documents in their tenant"
    )
    can_edit_global_docs: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        comment="Can edit global documents"
    )
    can_trigger_reindex: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        comment="Can trigger reindexing operations"
    )
    can_manage_users: Mapped[bool] = mapped_column(
        Boolean, 
        default=False,
        comment="Can manage users, roles, and flags"
    )

    # Системные поля
    require_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

class AuditLogs(Base):
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Актор и контекст
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=True, 
        comment="Tenant ID (null for global operations)"
    )
    
    # Действие
    action: Mapped[str] = mapped_column(String(100), comment="Action: create, update, delete, reindex")
    object_type: Mapped[str] = mapped_column(String(50), comment="Object type: document, chunk, user, etc.")
    object_id: Mapped[str] = mapped_column(String, comment="Object identifier")
    
    # Контекст действия
    scope_snapshot: Mapped[str] = mapped_column(
        String(20), 
        nullable=True,
        comment="Document scope: local, global"
    )
    
    # Метаданные
    meta: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)
    request_id: Mapped[str] = mapped_column(String, nullable=True)
    
    # Клиентская информация
    ip: Mapped[str] = mapped_column(String, nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Временная метка
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    
    # Индексы для эффективных запросов
    __table_args__ = (
        Index('idx_audit_logs_actor_user_id', 'actor_user_id'),
        Index('idx_audit_logs_tenant_id', 'tenant_id'),
        Index('idx_audit_logs_object_type', 'object_type'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_created_at', 'created_at'),
        Index('idx_audit_logs_object_lookup', 'object_type', 'object_id'),
    )