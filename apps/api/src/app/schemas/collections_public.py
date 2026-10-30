"""Allowlisted application collection projection, distinct from admin configuration."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CollectionWorkspace(BaseModel):
    id: UUID
    name: str


class CollectionWorkspacesResponse(BaseModel):
    items: list[CollectionWorkspace]


class PublishedCollectionVersion(BaseModel):
    number: int
    status: Literal['published'] = 'published'


class PublicCollectionSource(BaseModel):
    name: str
    type: str


class PublicCollectionReadiness(BaseModel):
    status: str = 'unknown'


class PublicCollectionCount(BaseModel):
    value: int | None = None
    kind: str | None = None
    unit: str | None = None


class PublicCollectionField(BaseModel):
    name: str
    data_type: str
    required: bool = False


class CollectionCapabilities(BaseModel):
    view_content: bool = False
    can_edit_content: bool = False
    view_schema: bool = False
    upload_documents: bool = False
    delete_documents: bool = False
    ingest: bool = False
    manage_memory: bool = False
    upload_csv: bool = False
    mutate_rows: bool = False
    reindex: bool = False
    upload_templates: bool = False
    analyze_templates: bool = False
    approve_templates: bool = False
    edit_templates: bool = False
    delete_templates: bool = False
    download: bool = False


class PublicCollectionResponse(BaseModel):
    # Identifiers are transport/navigation bindings, not ordinary display metadata.
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    collection_type: str
    description: str | None = None
    purpose: str | None = None
    version: PublishedCollectionVersion | None = None
    source: PublicCollectionSource | None = None
    locality: Literal['local', 'remote', 'virtual']
    readiness: PublicCollectionReadiness = Field(default_factory=PublicCollectionReadiness)
    count: PublicCollectionCount = Field(default_factory=PublicCollectionCount)
    fields: list[PublicCollectionField] = Field(default_factory=list)
    capabilities: CollectionCapabilities = Field(default_factory=CollectionCapabilities)
    capability_reasons: dict[str, str] = Field(default_factory=dict)


class PublicCollectionListResponse(BaseModel):
    items: list[PublicCollectionResponse]
    total: int
