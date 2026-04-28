"""Pydantic schemas for Collections API."""
from typing import Any, Optional, List, Literal
import uuid
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.models.collection import CollectionType, CollectionVersionStatus, FieldCategory, FieldType


class FieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    category: str = Field(
        default=FieldCategory.USER.value,
        pattern="^(specific|user)$",
    )
    data_type: str = Field(
        ...,
        pattern="^(string|text|integer|float|boolean|datetime|date|enum|json|file)$",
    )
    required: bool = False
    description: Optional[str] = None
    filterable: bool = False
    sortable: bool = False
    used_in_retrieval: bool = False
    used_in_prompt_context: bool = False

    @model_validator(mode="after")
    def validate_field(self) -> "FieldSchema":
        if self.category == FieldCategory.SPECIFIC.value:
            if (
                self.filterable
                or self.sortable
                or self.used_in_prompt_context
                or self.used_in_retrieval
            ):
                raise ValueError(
                    "Specific fields cannot be filterable, sortable, retrieval-enabled, or prompt-visible"
                )

        if self.data_type == FieldType.FILE.value:
            if self.filterable or self.sortable or self.used_in_prompt_context:
                raise ValueError("File fields cannot be filterable, sortable, or prompt-visible")

        if self.used_in_retrieval and self.data_type not in (FieldType.TEXT.value,):
            raise ValueError("used_in_retrieval is only available for text fields in base collection schema")

        if self.sortable and self.data_type in (FieldType.FILE.value, FieldType.JSON.value):
            raise ValueError("Sortable fields must not be file/json")

        if self.filterable and self.data_type == FieldType.FILE.value:
            raise ValueError("File fields cannot be filterable")

        return self


class VectorConfigSchema(BaseModel):
    """Configuration for vector search"""
    chunk_strategy: str = Field(default="by_paragraphs", pattern="^(by_tokens|by_paragraphs|by_sentences|by_markdown)$")
    chunk_size: int = Field(default=512, ge=128, le=2048)
    overlap: int = Field(default=50, ge=0, le=512)
    

class CreateCollectionRequest(BaseModel):
    tenant_id: Optional[uuid.UUID] = None
    collection_type: str = Field(
        default=CollectionType.TABLE.value,
        pattern=r"^(table|document|sql|api)$",
    )
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fields: List[FieldSchema] = Field(default_factory=list)
    source_contract: Optional[dict] = None
    vector_config: Optional[VectorConfigSchema] = None
    table_schema: Optional[dict] = None
    # Required FK: each collection is bound to a data instance.
    data_instance_id: uuid.UUID


class SchemaOperation(BaseModel):
    op: Literal["add", "alter", "rename", "remove"]
    name: Optional[str] = None
    new_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    field: Optional[FieldSchema] = None

    @model_validator(mode="after")
    def validate_operation(self) -> "SchemaOperation":
        if self.op == "add":
            if self.field is None:
                raise ValueError("field is required for add operation")
            if self.name or self.new_name:
                raise ValueError("add operation must only define field")
        elif self.op == "alter":
            if not self.name or self.field is None:
                raise ValueError("alter operation requires name and field")
            if self.field.name != self.name:
                raise ValueError("alter operation field.name must match name")
            if self.new_name:
                raise ValueError("alter operation must not define new_name")
        elif self.op == "rename":
            if not self.name or not self.new_name:
                raise ValueError("rename operation requires name and new_name")
            if self.field is not None:
                raise ValueError("rename operation must not define field")
        elif self.op == "remove":
            if not self.name:
                raise ValueError("remove operation requires name")
            if self.field is not None or self.new_name:
                raise ValueError("remove operation must only define name")
        return self


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    table_name: Optional[str] = None
    table_schema: Optional[dict] = None
    schema_ops: List[SchemaOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_non_empty(self) -> "UpdateCollectionRequest":
        has_metadata_patch = bool(
            self.model_fields_set
            & {"name", "description", "is_active", "table_name", "table_schema"}
        )
        if not has_metadata_patch and not self.schema_ops:
            raise ValueError("At least one mutable collection property or schema operation is required")
        return self


class CollectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    collection_type: str = CollectionType.TABLE.value
    slug: str
    name: str
    description: Optional[str]
    fields: List[dict]
    source_contract: Optional[dict] = None
    status: str
    status_details: Optional[dict] = None
    runtime_readiness: Optional[dict] = None
    table_name: Optional[str] = None
    table_schema: Optional[dict] = None
    
    # Vector search fields
    has_vector_search: bool
    vector_config: Optional[dict] = None
    qdrant_collection_name: Optional[str] = None
    
    # Vectorization statistics (local only)
    total_rows: Optional[int] = None
    vectorized_rows: Optional[int] = None
    total_chunks: Optional[int] = None
    failed_rows: Optional[int] = None
    vectorization_progress: float = 0.0
    is_fully_vectorized: bool = False
    
    # Instance link
    data_instance_id: uuid.UUID
    data_instance: Optional["DataInstanceShort"] = None
    
    # Remote collection fields
    last_sync_at: Optional[str] = None
    
    is_active: bool
    current_version_id: Optional[uuid.UUID] = None
    current_version: Optional["CollectionVersionResponse"] = None
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class CollectionListResponse(BaseModel):
    items: List[CollectionResponse]
    total: int
    page: int
    size: int
    has_more: bool


class DataInstanceShort(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class VectorCollectionAuditEntry(BaseModel):
    qdrant_collection_name: str
    collection_id: Optional[uuid.UUID] = None
    collection_slug: Optional[str] = None
    collection_type: Optional[str] = None
    detail: Optional[str] = None


class VectorCollectionAuditResponse(BaseModel):
    expected_count: int
    actual_count: int
    missing_in_qdrant: List[VectorCollectionAuditEntry] = Field(default_factory=list)
    orphan_in_qdrant: List[VectorCollectionAuditEntry] = Field(default_factory=list)
    non_vector_with_qdrant: List[VectorCollectionAuditEntry] = Field(default_factory=list)
    cleaned_orphan_count: int = 0


class CollectionTypePresetResponse(BaseModel):
    collection_type: str
    fields: List[dict] = Field(default_factory=list)


class CollectionTypePresetsResponse(BaseModel):
    items: List[CollectionTypePresetResponse] = Field(default_factory=list)


class DiscoveredSqlTable(BaseModel):
    schema_name: str
    table_name: str
    object_type: str = "BASE TABLE"
    table_schema: dict = Field(default_factory=dict)


class DiscoverSqlTablesResponse(BaseModel):
    items: List[DiscoveredSqlTable] = Field(default_factory=list)
    total: int = 0


class DiscoveredApiEntity(BaseModel):
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class DiscoverApiEntitiesResponse(BaseModel):
    items: List[DiscoveredApiEntity] = Field(default_factory=list)
    total: int = 0


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.splitlines()
    else:
        raw_items = []

    result: list[str] = []
    for item in raw_items:
        normalized = _normalize_text(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


class CollectionVersionCreate(BaseModel):
    data_description: Optional[str] = Field(
        default=None,
        description="Что это за данные в коллекции (человеко-читаемо, без JSON-схем).",
    )
    usage_purpose: Optional[str] = Field(
        default=None,
        description="Зачем эти данные нужны в рантайме и какие задачи покрывают.",
    )
    notes: Optional[str] = None


class CollectionVersionUpdate(BaseModel):
    data_description: Optional[str] = Field(
        default=None,
        description="Что это за данные в коллекции (человеко-читаемо, без JSON-схем).",
    )
    usage_purpose: Optional[str] = Field(
        default=None,
        description="Зачем эти данные нужны в рантайме и какие задачи покрывают.",
    )
    notes: Optional[str] = None


class CollectionVersionResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    version: int
    status: str = CollectionVersionStatus.DRAFT.value
    data_description: Optional[str] = None
    usage_purpose: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


CollectionResponse.model_rebuild()
