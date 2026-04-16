"""
Typed dataclasses for stage-to-stage payload in RAG ingest pipeline.

Each stage produces a typed result that the next stage consumes.
These replace the untyped Dict[str, Any] that was previously passed between tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ExtractResult:
    """Result of extract stage → consumed by normalize."""
    source_id: str
    extracted_key: str
    extractor_kind: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "extracted_key": self.extracted_key,
            "extractor_kind": self.extractor_kind,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractResult:
        return cls(
            source_id=data["source_id"],
            extracted_key=data.get("extracted_key", ""),
            extractor_kind=data.get("extractor_kind", ""),
            warnings=data.get("warnings", []),
        )


@dataclass(frozen=True)
class NormalizeResult:
    """Result of normalize stage → consumed by chunk."""
    source_id: str
    canonical_key: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "canonical_key": self.canonical_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NormalizeResult:
        return cls(
            source_id=data["source_id"],
            canonical_key=data.get("canonical_key", ""),
        )


@dataclass(frozen=True)
class ChunkResult:
    """Result of chunk stage → consumed by embed."""
    source_id: str
    chunks_key: str
    chunk_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "chunks_key": self.chunks_key,
            "chunk_count": self.chunk_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChunkResult:
        return cls(
            source_id=data["source_id"],
            chunks_key=data.get("chunks_key", ""),
            chunk_count=data.get("chunk_count", 0),
        )


@dataclass(frozen=True)
class EmbedResult:
    """Result of embed stage → consumed by index."""
    source_id: str
    model_alias: str
    embeddings_key: str
    count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "model_alias": self.model_alias,
            "embeddings_key": self.embeddings_key,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmbedResult:
        return cls(
            source_id=data["source_id"],
            model_alias=data.get("model_alias", ""),
            embeddings_key=data.get("embeddings_key", ""),
            count=data.get("count", 0),
        )


@dataclass(frozen=True)
class IndexResult:
    """Result of index stage — terminal."""
    source_id: str
    model_alias: str
    indexed_count: int = 0
    collection: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "model_alias": self.model_alias,
            "indexed_count": self.indexed_count,
            "collection": self.collection,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IndexResult:
        return cls(
            source_id=data["source_id"],
            model_alias=data.get("model_alias", ""),
            indexed_count=data.get("indexed_count", 0),
            collection=data.get("collection", ""),
        )
