"""
ToolInstance — универсальный ресурс платформы.

Три рабочие оси:
- instance_kind: data | service
- placement: local | remote
- domain: llm | mcp | collection.document | collection.table | rag | jira | netbox | dcbox

Placement определяет операционную модель:
- LOCAL: system-managed platform resource
- REMOTE: user-managed external system

Semantic layer больше не живёт на инстансе.
Локальные data-инстансы получают смысл через связанную Collection (FK),
а service-инстансы описывают только доступ/провайдера.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class InstanceKind(str, Enum):
    """Instance type / role (legacy)"""
    DATA = "data"
    SERVICE = "service"


class ConnectorType(str, Enum):
    """Connector type"""
    DATA = "data"
    MCP = "mcp"
    MODEL = "model"


class ConnectorSubtype(str, Enum):
    """Data connector subtype"""
    SQL = "sql"
    API = "api"


class InstancePlacement(str, Enum):
    """Instance placement — operational model"""
    LOCAL = "local"
    REMOTE = "remote"


class InstanceDomain(str, Enum):
    """Instance domain — subject specialization"""
    LLM = "llm"
    SQL = "sql"
    MCP = "mcp"
    COLLECTION_DOCUMENT = "collection.document"
    COLLECTION_TABLE = "collection.table"
    RAG = "rag"
    JIRA = "jira"
    NETBOX = "netbox"
    DCBOX = "dcbox"


class ToolInstance(Base):
    """
    Универсальный ресурс платформы (v3).

    Примеры:
    - service.remote.llm   — OpenAI provider
    - service.remote.mcp   — MCP Jira gateway
    - data.sql             — external SQL database
    - data.remote.jira     — Jira Prod (source)
    - data.local.rag       — RAG knowledge base
    - data.local.collection.document — doc collection
    - data.local.collection.table    — table collection

    Креды привязываются через Credential (owner-based).
    Локальные инстансы не требуют кредов.
    """
    __tablename__ = "tool_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── v3 classification axes ───────────────────────────────────────────
    instance_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default='data',
        comment="Instance role: data | service"
    )
    connector_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default='data',
        comment="Connector type: data | mcp | model"
    )
    connector_subtype: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Data connector subtype: sql | api"
    )
    placement: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default='remote',
        comment="Operational model: local | remote"
    )
    domain: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default='rag',
        comment="Transitional classification tag: llm, mcp, collection.document, jira, etc."
    )

    # ── Connection ───────────────────────────────────────────────────────
    url: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ── Linking data → service ───────────────────────────────────────────
    access_via_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Service instance used to access this data instance"
    )

    # ── Lifecycle ────────────────────────────────────────────────────────
    health_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────────
    access_via: Mapped[Optional["ToolInstance"]] = relationship(
        "ToolInstance",
        remote_side=[id],
        foreign_keys=[access_via_instance_id]
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tool_instance_slug"),
        CheckConstraint(
            "instance_kind IN ('data', 'service')",
            name="ck_instance_kind"
        ),
        CheckConstraint(
            "connector_type IN ('data', 'mcp', 'model')",
            name="ck_connector_type"
        ),
        CheckConstraint(
            "connector_subtype IS NULL OR connector_subtype IN ('sql', 'api')",
            name="ck_connector_subtype"
        ),
        CheckConstraint(
            "placement IN ('local', 'remote')",
            name="ck_instance_placement"
        ),
    )

    @property
    def is_local(self) -> bool:
        return self.placement == InstancePlacement.LOCAL.value

    @property
    def is_remote(self) -> bool:
        return self.placement == InstancePlacement.REMOTE.value

    @property
    def is_data(self) -> bool:
        connector_type = str(getattr(self, "connector_type", "") or "").strip().lower()
        if connector_type:
            return connector_type == ConnectorType.DATA.value
        return self.instance_kind == InstanceKind.DATA.value

    @property
    def is_service(self) -> bool:
        connector_type = str(getattr(self, "connector_type", "") or "").strip().lower()
        if connector_type:
            return connector_type in {
                ConnectorType.MCP.value,
                ConnectorType.MODEL.value,
            }
        return self.instance_kind == InstanceKind.SERVICE.value

    @property
    def is_mcp_connector(self) -> bool:
        connector_type = str(getattr(self, "connector_type", "") or "").strip().lower()
        if connector_type:
            return connector_type == ConnectorType.MCP.value
        return self.instance_kind == InstanceKind.SERVICE.value and str(self.domain or "").strip().lower() == "mcp"

    @property
    def is_model_connector(self) -> bool:
        connector_type = str(getattr(self, "connector_type", "") or "").strip().lower()
        if connector_type:
            return connector_type == ConnectorType.MODEL.value
        return self.instance_kind == InstanceKind.SERVICE.value and str(self.domain or "").strip().lower() == "llm"

    def __repr__(self) -> str:
        return f"<ToolInstance {self.connector_type}.{self.placement}.{self.domain} '{self.name}'>"
