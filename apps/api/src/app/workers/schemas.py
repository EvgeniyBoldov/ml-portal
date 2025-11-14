"""
Worker schemas for RAG ingest pipeline
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


class ChunkProfile(str, Enum):
    """Chunking profiles"""
    BY_TOKENS = "by_tokens"
    BY_SENTENCES = "by_sentences"
    BY_PARAGRAPHS = "by_paragraphs"


@dataclass
class BatchInfo:
    """Batch processing information"""
    batch_size: int
    total_items: int
    current_batch: int
    processed_items: int


@dataclass
class ChunkData:
    """Chunk data structure"""
    text: str
    start_pos: int
    end_pos: int
    page: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EmbeddingResult:
    """Embedding result"""
    chunk_id: str
    vector: List[float]
    model_alias: str
    model_version: str
    dimensions: int


@dataclass
class ReindexIn:
    """Reindex input data"""
    source_id: str
    tenant_id: str
    models: List[str]
    force: bool = False