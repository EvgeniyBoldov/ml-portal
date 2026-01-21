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
    VECTOR = "vector"


class Collection(Base):
    """
    Metadata for a dynamic data collection.
    
    Fields schema example:
    [
        {
            "name": "title",
            "type": "text",
            "required": true,
            "search_modes": ["exact", "like"],
            "description": "Ticket title"
        },
        {
            "name": "description",
            "type": "text",
            "required": false,
            "search_modes": ["like", "vector"],
            "description": "Ticket description (large text field)"
        },
        {
            "name": "status",
            "type": "text",
            "required": true,
            "search_modes": ["exact"],
            "description": "Ticket status"
        },
        {
            "name": "created_at",
            "type": "datetime",
            "required": false,
            "search_modes": ["exact", "range"],
            "description": "When the ticket was created"
        }
    ]
    
    Vector search is automatically enabled if any field has 'vector' in search_modes.
    Vector fields must be 'text' type and must also have 'like' in search_modes.
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
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Vector search configuration (optional)
    vector_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    qdrant_collection_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Vectorization statistics
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vectorized_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def get_required_fields(self) -> List[dict]:
        """Return only required fields"""
        return [f for f in self.fields if f.get("required", False)]

    def get_field_by_name(self, name: str) -> Optional[dict]:
        """Get field definition by name"""
        for f in self.fields:
            if f.get("name") == name:
                return f
        return None
    
    def get_fields_by_search_mode(self, mode: str) -> List[dict]:
        """Get fields that support specific search mode"""
        return [
            f for f in self.fields 
            if mode in f.get("search_modes", [])
        ]
    
    @property
    def has_vector_search(self) -> bool:
        """Check if collection has any vector search fields"""
        return any(
            "vector" in field.get("search_modes", []) 
            for field in self.fields
        )
    
    @property
    def vector_fields(self) -> List[str]:
        """Get list of field names that support vector search"""
        return [
            field["name"] 
            for field in self.fields 
            if "vector" in field.get("search_modes", [])
        ]
    
    @property
    def searchable_fields_by_mode(self) -> dict:
        """Group searchable fields by search mode"""
        result = {
            "exact": [],
            "like": [],
            "range": [],
            "vector": []
        }
        for field in self.fields:
            for mode in field.get("search_modes", []):
                if mode in result:
                    result[mode].append(field["name"])
        return result
    
    @property
    def vectorization_progress(self) -> float:
        """Calculate vectorization progress percentage"""
        if self.total_rows == 0:
            return 0.0
        return (self.vectorized_rows / self.total_rows) * 100
    
    @property
    def is_fully_vectorized(self) -> bool:
        """Check if all rows are vectorized"""
        return (
            self.has_vector_search and 
            self.total_rows > 0 and 
            self.vectorized_rows == self.total_rows
        )
