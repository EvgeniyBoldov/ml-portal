"""Normalized, content-free metadata exposed for chat artifacts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ArtifactOriginKind = Literal["user_upload", "agent_generated", "rag_document", "external_file"]


class ArtifactOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ArtifactOriginKind
    source_id: str
    source_type: str | None = None
    collection_id: str | None = None
    created_by_run_id: str | None = None


class ArtifactFileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    media_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class ArtifactDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=600)
    source: Literal["model_inferred", "source_metadata"]
    representation_id: str | None = None


class ArtifactRepresentationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_fingerprint: str
    extraction_profile: str
    status: Literal["ready", "partial", "unreadable"]


class ChatArtifactManifest(BaseModel):
    """Compact artifact passport; extracted file text never belongs here."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    artifact_id: str
    origin: ArtifactOrigin
    file: ArtifactFileMetadata
    description: ArtifactDescription | None = None
    representation: ArtifactRepresentationMetadata | None = None
    status: str = "ready"
    attributes: dict[str, Any] = Field(default_factory=dict)
