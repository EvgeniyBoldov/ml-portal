from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from .base import Base


class TemplateAnalysisStatus(Base):
    """Task status nodes for template analysis lifecycle."""

    __tablename__ = "template_analysis_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    row_id = Column(UUID(as_uuid=True), nullable=False)
    node_key = Column(String(50), nullable=False)  # description | schema
    status = Column(String(20), nullable=False)  # pending | queued | processing | completed | failed | cancelled
    celery_task_id = Column(String(50), nullable=True)
    error_short = Column(Text, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("row_id", "node_key", name="uq_template_analysis_statuses_row_node"),
        Index("ix_template_analysis_statuses_collection_id", "collection_id"),
        Index("ix_template_analysis_statuses_row_id", "row_id"),
        Index("ix_template_analysis_statuses_status", "status"),
        Index("ix_template_analysis_statuses_updated_at", "updated_at"),
    )
