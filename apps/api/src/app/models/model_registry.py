"""
Model Registry SQLAlchemy model
"""
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from datetime import datetime
from .base import Base


class ModelRegistry(Base):
    """Model registry table for managing ML models"""
    __tablename__ = "model_registry"
    __table_args__ = {'extend_existing': True}
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # model id from manifest
    version: Mapped[str] = mapped_column(String(50))
    modality: Mapped[str] = mapped_column(String(20))  # text|image|layout|table|rerank
    state: Mapped[str] = mapped_column(String(20), default="active")  # active|archived|retired|disabled
    vector_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[str] = mapped_column(String(500))  # full path to model directory
    default_for_new: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
