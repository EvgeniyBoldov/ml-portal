"""
Common schemas and enums for ML Portal
"""
from enum import Enum
from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel


class ProblemDetails(BaseModel):
    """Standard problem details for API errors"""
    type: Optional[str] = None
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None
    errors: Optional[Dict[str, Any]] = None


class DocumentStatus(str, Enum):
    """Document processing status"""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    CANCELED = "canceled"


class Step(str, Enum):
    """Processing steps"""
    EXTRACT = "extract"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"


class IngestRunStatus(str, Enum):
    """Ingest run status"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ChunkProfile(str, Enum):
    """Chunking profiles"""
    BY_TOKENS = "by_tokens"
    BY_SENTENCES = "by_sentences"
    BY_PARAGRAPHS = "by_paragraphs"
    BY_PAGES = "by_pages"


class EmbeddingModel(str, Enum):
    """Embedding models"""
    MINILM_L6_V2 = "all-MiniLM-L6-v2"
    MINILM_L12_V2 = "all-MiniLM-L12-v2"
    MPNET_BASE_V2 = "all-mpnet-base-v2"


class QueuePriority(int, Enum):
    """Queue priorities"""
    CRITICAL = 10
    HIGH = 8
    MEDIUM = 5
    LOW = 2
    MAINTENANCE = 1