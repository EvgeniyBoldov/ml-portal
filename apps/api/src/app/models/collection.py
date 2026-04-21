"""Collection model — first-class data asset (local and remote)."""
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    func,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class CollectionType(str, Enum):
    """Supported collection types."""
    TABLE = "table"
    DOCUMENT = "document"
    SQL = "sql"
    API = "api"


class CollectionStatus(str, Enum):
    """Operational readiness state of a collection."""
    CREATED = "created"
    DISCOVERED = "discovered"
    INGESTING = "ingesting"
    READY = "ready"
    DEGRADED = "degraded"
    ERROR = "error"


class CollectionVersionStatus(str, Enum):
    """Version lifecycle for collection semantic/runtime params."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class FieldCategory(str, Enum):
    """Logical field categories inside a collection schema."""
    SYSTEM = "system"
    SPECIFIC = "specific"
    USER = "user"


class FieldType(str, Enum):
    """Supported collection data types."""
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    ENUM = "enum"
    JSON = "json"
    FILE = "file"


class FilterOperator(str, Enum):
    """Supported filter operators for DSL"""
    EQ = "eq"              # Equal
    NEQ = "neq"            # Not equal
    IN = "in"              # In list
    NOT_IN = "not_in"      # Not in list
    LIKE = "like"          # LIKE pattern
    CONTAINS = "contains"  # Contains substring (ILIKE %value%)
    GT = "gt"              # Greater than
    GTE = "gte"            # Greater than or equal
    LT = "lt"              # Less than
    LTE = "lte"            # Less than or equal
    RANGE = "range"        # Range (gte + lt)
    IS_NULL = "is_null"    # Is null / is not null


class Collection(Base):
    """
    First-class data asset of the platform.

    Collection describes scope of data, schema, and semantic layer.
    Can represent:
    - local structured records (table)
    - local document registry (document)
    - SQL-backed table asset (sql)
    - API resource catalog asset (api)

    Instance layer (ToolInstance) describes WHERE data lives and HOW to connect.
    Collection describes WHAT the data means.

    `fields` stores the explicit non-system schema. Each field is expected to have:
    - `name`
    - `category`
    - `data_type`
    - `required`
    - `description`
    - `filterable`
    - `sortable`
    - `used_in_retrieval`
    - `used_in_prompt_context`

    System/platform fields exist logically, but are not persisted in `fields`.
    """
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    collection_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=CollectionType.TABLE.value
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collection_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    table_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Vector search configuration (optional)
    vector_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    qdrant_collection_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Vectorization statistics (local collections only)
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    vectorized_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    failed_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    
    # Primary key and time column configuration (local collections only)
    primary_key_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="id")
    time_column: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Default sort configuration: {"field": "created_at", "order": "desc"}
    default_sort: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Entity type for LLM context (e.g., "ticket", "device", "user")
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Guardrails (local collections only)
    allow_unfiltered_search: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    max_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=100)
    query_timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=10)
    
    # Source-of-truth runtime binding: collection -> data instance.
    data_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_instances.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    
    # SQL collection fields
    table_schema: Mapped[Optional[dict]] = mapped_column(
        "discovered_schema",
        JSONB,
        nullable=True,
        comment="Table schema / discovered SQL shape",
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last schema sync timestamp for remote collections"
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    schema: Mapped[Optional["CollectionSchema"]] = relationship(
        "CollectionSchema",
        back_populates="collection",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    versions: Mapped[List["CollectionVersion"]] = relationship(
        "CollectionVersion",
        back_populates="collection",
        foreign_keys="CollectionVersion.collection_id",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[Optional["CollectionVersion"]] = relationship(
        "CollectionVersion",
        foreign_keys=[current_version_id],
        post_update=True,
        uselist=False,
    )
    data_instance: Mapped["ToolInstance"] = relationship(
        "ToolInstance",
        foreign_keys=[data_instance_id],
        lazy="joined",
    )

    def __init__(self, **kwargs):
        fields = kwargs.pop("fields", None)
        source_contract = kwargs.pop("source_contract", None)
        schema_status = kwargs.pop("schema_status", None)
        super().__init__(**kwargs)
        if fields is not None:
            self.fields = fields
        if source_contract is not None:
            self.source_contract = source_contract
        if schema_status is not None:
            self.schema_status = schema_status

    def _ensure_schema(self) -> "CollectionSchema":
        if self.schema is None:
            self.schema = CollectionSchema(
                fields=[],
                source_contract=None,
                schema_status=CollectionStatus.CREATED.value,
            )
        return self.schema

    @property
    def fields(self) -> List[dict]:
        if self.schema is None or self.schema.fields is None:
            return []
        return list(self.schema.fields)

    @fields.setter
    def fields(self, value: Optional[List[dict]]) -> None:
        schema = self._ensure_schema()
        schema.fields = list(value or [])

    @property
    def source_contract(self) -> Optional[dict]:
        if self.schema is None:
            return None
        return self.schema.source_contract

    @source_contract.setter
    def source_contract(self, value: Optional[dict]) -> None:
        schema = self._ensure_schema()
        schema.source_contract = value

    @property
    def schema_status(self) -> str:
        if self.schema is None:
            return CollectionStatus.CREATED.value
        return self.schema.schema_status

    @schema_status.setter
    def schema_status(self, value: str) -> None:
        schema = self._ensure_schema()
        schema.schema_status = value

    def get_required_fields(self) -> List[dict]:
        """Return required explicit fields."""
        return [f for f in self.fields if f.get("required", False)]

    def get_system_fields(self) -> List[dict]:
        """Return derived platform-owned record fields."""
        return [
            {
                "name": "id",
                "category": FieldCategory.SYSTEM.value,
                "data_type": FieldType.STRING.value,
                "required": True,
                "description": "Platform-owned record identifier",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
            {
                "name": "_created_at",
                "category": FieldCategory.SYSTEM.value,
                "data_type": FieldType.DATETIME.value,
                "required": True,
                "description": "Platform-owned record creation timestamp",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
            {
                "name": "_updated_at",
                "category": FieldCategory.SYSTEM.value,
                "data_type": FieldType.DATETIME.value,
                "required": True,
                "description": "Platform-owned record update timestamp",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
        ]

    def get_field_by_name(self, name: str) -> Optional[dict]:
        """Get field definition by name."""
        for f in self.fields:
            if f.get("name") == name:
                return f
        return None

    def get_fields_by_category(self, category: str) -> List[dict]:
        """Return fields of a given category, including derived system fields."""
        if category == FieldCategory.SYSTEM.value:
            return self.get_system_fields()
        return [f for f in self.fields if f.get("category") == category]

    def get_specific_fields(self) -> List[dict]:
        """Return type-owned immutable fields."""
        return self.get_fields_by_category(FieldCategory.SPECIFIC.value)

    def get_user_fields(self) -> List[dict]:
        """Return admin-defined business fields."""
        return self.get_fields_by_category(FieldCategory.USER.value)

    def get_business_fields(self) -> List[dict]:
        """Fields that participate in business semantics."""
        return [*self.get_specific_fields(), *self.get_user_fields()]

    def get_schema_mutable_fields(self) -> List[dict]:
        """Fields whose schema may evolve through controlled admin changes."""
        return self.get_user_fields()

    def get_row_writable_fields(self) -> List[dict]:
        """Fields writable through normal admin/data ingest paths."""
        return self.get_business_fields()

    def get_mutable_fields(self) -> List[dict]:
        """Backward-compatible alias for writable non-system fields."""
        return self.get_row_writable_fields()

    def get_filterable_fields(self) -> List[dict]:
        """Business fields allowed in filtering."""
        return [f for f in self.get_business_fields() if f.get("filterable", False)]

    def get_sortable_fields(self) -> List[dict]:
        """Business fields allowed in sorting."""
        return [f for f in self.get_business_fields() if f.get("sortable", False)]

    def get_prompt_context_fields(self) -> List[dict]:
        """Fields that may appear in agent-facing context."""
        return [f for f in self.get_business_fields() if f.get("used_in_prompt_context", False)]

    @property
    def is_local(self) -> bool:
        """Local collections: platform manages storage."""
        return self.collection_type in (CollectionType.TABLE.value, CollectionType.DOCUMENT.value, CollectionType.SQL.value)

    @property
    def is_remote(self) -> bool:
        """Remote collections: external system owns storage."""
        return not self.is_local

    @property
    def is_document_collection(self) -> bool:
        """Check if this is a document collection."""
        return self.collection_type == CollectionType.DOCUMENT.value

    @property
    def file_fields(self) -> List[str]:
        """Get names of explicit file fields."""
        return [
            field["name"]
            for field in self.fields
            if field.get("data_type") == FieldType.FILE.value
        ]

    @property
    def has_vector_search(self) -> bool:
        """Check if collection needs retrieval/vector processing."""
        if self.is_document_collection:
            return True
        return any(
            field.get("used_in_retrieval", False)
            and field.get("data_type") == FieldType.TEXT.value
            for field in self.get_business_fields()
        )

    @property
    def vector_fields(self) -> List[str]:
        """Get text fields that participate in retrieval/vector indexing."""
        return [
            field["name"]
            for field in self.get_business_fields()
            if field.get("used_in_retrieval", False)
            and field.get("data_type") == FieldType.TEXT.value
        ]

    @property
    def vectorization_progress(self) -> float:
        """Calculate vectorization progress percentage."""
        total = self.total_rows or 0
        if total == 0:
            return 0.0
        return ((self.vectorized_rows or 0) / total) * 100

    @property
    def is_fully_vectorized(self) -> bool:
        """Check if all rows are vectorized."""
        total = self.total_rows or 0
        return (
            self.has_vector_search and
            total > 0 and
            (self.vectorized_rows or 0) == total
        )


class CollectionSchema(Base):
    """Non-versioned structural contract of a collection."""

    __tablename__ = "collection_schemas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_contract: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="External schema contract snapshot (e.g. remote SQL DDL / discovered source contract)",
    )
    schema_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CollectionStatus.CREATED.value,
        server_default=CollectionStatus.CREATED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    collection: Mapped["Collection"] = relationship(
        "Collection",
        back_populates="schema",
        foreign_keys=[collection_id],
    )


class CollectionVersion(Base):
    """Semantic/runtime version of collection (contract remains in CollectionSchema)."""

    __tablename__ = "collection_versions"
    __table_args__ = (
        UniqueConstraint("collection_id", "version", name="uq_collection_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CollectionVersionStatus.DRAFT.value,
        server_default=CollectionVersionStatus.DRAFT.value,
        index=True,
    )
    retrieval_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_context_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    collection: Mapped["Collection"] = relationship(
        "Collection",
        back_populates="versions",
        foreign_keys=[collection_id],
    )
