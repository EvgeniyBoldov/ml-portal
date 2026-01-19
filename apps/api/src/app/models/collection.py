"""
Collection model for dynamic data collections
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import String, Text, Boolean, Integer, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CollectionType(str, Enum):
    SQL = "sql"
    VECTOR = "vector"
    HYBRID = "hybrid"


class FieldType(str, Enum):
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"


class SearchMode(str, Enum):
    EXACT = "exact"
    LIKE = "like"
    RANGE = "range"


class Collection(Base):
    """
    Metadata for a dynamic data collection.
    
    Fields schema example:
    [
        {
            "name": "title",
            "type": "text",
            "required": true,
            "searchable": true,
            "search_mode": "like",
            "description": "Ticket title"
        },
        {
            "name": "started_at",
            "type": "datetime",
            "required": false,
            "searchable": true,
            "search_mode": "range",
            "description": "When the ticket was created"
        }
    ]
    """
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CollectionType.SQL.value
    )
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def get_searchable_fields(self) -> List[dict]:
        """Return only fields that are searchable"""
        return [f for f in self.fields if f.get("searchable", False)]

    def get_required_fields(self) -> List[dict]:
        """Return only required fields"""
        return [f for f in self.fields if f.get("required", False)]

    def get_field_by_name(self, name: str) -> Optional[dict]:
        """Get field definition by name"""
        for f in self.fields:
            if f.get("name") == name:
                return f
        return None
