"""
Tool model v2 - publication container for tool releases.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.discovered_tool import DiscoveredTool
    from app.models.tool_release import ToolBackendRelease, ToolRelease


class Tool(Base):
    """
    Tool container - holds publication identity and curated releases.

    Версионирование через ToolRelease.
    current_version_id указывает на активную версию.
    """
    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Info (for humans) ───────────────────────────────────────────────
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    domains: Mapped[List[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'::varchar[]"),
        comment="Runtime domains / tags used for grouping and routing",
    )

    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_releases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    backend_releases: Mapped[List["ToolBackendRelease"]] = relationship(
        "ToolBackendRelease",
        back_populates="tool",
        foreign_keys="ToolBackendRelease.tool_id",
        cascade="all, delete-orphan"
    )

    discovered_tools: Mapped[List["DiscoveredTool"]] = relationship(
        "DiscoveredTool",
        back_populates="tool",
        foreign_keys="DiscoveredTool.tool_id",
    )

    releases: Mapped[List["ToolRelease"]] = relationship(
        "ToolRelease",
        back_populates="tool",
        foreign_keys="ToolRelease.tool_id",
        cascade="all, delete-orphan"
    )

    current_version: Mapped[Optional["ToolRelease"]] = relationship(
        "ToolRelease",
        foreign_keys=[current_version_id],
        post_update=True
    )

    def __repr__(self):
        return f"<Tool {self.slug}>"
