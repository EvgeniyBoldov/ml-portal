"""
DiscoveredTool — raw capability snapshot from discovery sources.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool import Tool
    from app.models.tool_instance import ToolInstance


class DiscoveredTool(Base):
    """
    Raw discovered capability (local + MCP).

    source='local'  — из ToolRegistry, provider_instance_id=NULL
    source='mcp'    — из MCP-провайдера, provider_instance_id → ToolInstance(service.remote.mcp)
    """
    __tablename__ = "discovered_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="Tool slug (e.g. 'collection.search', 'jira.issues.list')"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional publication container link. NULL means discovered but unpublished.",
    )

    # ── Source ─────────────────────────────────────────────────────────────
    source: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="local | mcp"
    )
    provider_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_instances.id", ondelete="CASCADE"),
        nullable=True, index=True,
        comment="MCP provider ToolInstance (NULL for local tools)"
    )

    # ── Domain linkage ─────────────────────────────────────────────────────
    domains: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}",
        comment="Business domains this tool serves (e.g. ['collection.table', 'rag'])"
    )

    # ── Schema ─────────────────────────────────────────────────────────────
    input_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="JSON Schema for input parameters"
    )
    output_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="JSON Schema for output"
    )

    # ── Lifecycle ──────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="False if tool disappeared on last rescan"
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When tool was last seen during scan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    tool: Mapped[Optional["Tool"]] = relationship(
        "Tool",
        back_populates="discovered_tools",
        foreign_keys=[tool_id],
    )
    provider_instance: Mapped[Optional["ToolInstance"]] = relationship(
        "ToolInstance",
        foreign_keys=[provider_instance_id],
        lazy="joined",
    )

    __table_args__ = (
        Index(
            "uq_discovered_local_slug_null_provider",
            "slug",
            unique=True,
            postgresql_where=provider_instance_id.is_(None),
        ),
        Index(
            "uq_discovered_slug_provider",
            "slug", "provider_instance_id",
            unique=True,
            postgresql_where=provider_instance_id.isnot(None),
        ),
    )

    def __repr__(self) -> str:
        return f"<DiscoveredTool {self.source}:{self.slug}>"
