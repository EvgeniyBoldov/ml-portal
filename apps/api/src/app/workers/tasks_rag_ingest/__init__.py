"""Task entry points for RAG ingest pipeline."""

from .extract import extract_document
from .normalize import normalize_document
from .chunk import chunk_document
from .embed import embed_chunks_model
from .index import index_model, commit_source
from .cleanup import cleanup_document_artifacts

__all__ = [
    "extract_document",
    "normalize_document",
    "chunk_document",
    "embed_chunks_model",
    "index_model",
    "commit_source",
    "cleanup_document_artifacts",
]
