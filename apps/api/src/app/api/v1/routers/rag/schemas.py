"""
RAG Pydantic schemas for API responses.
"""
from __future__ import annotations
from typing import Any, Optional, List, Dict
from pydantic import BaseModel


class StatusNode(BaseModel):
    """Status node in the graph"""
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str
    model_version: Optional[str] = None


class PipelineStage(BaseModel):
    """Pipeline stage status"""
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str


class EmbeddingModel(BaseModel):
    """Embedding model status"""
    model: str
    version: Optional[str] = None
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str


class StatusGraphResponse(BaseModel):
    """Response model for status graph"""
    doc_id: str
    pipeline: List[PipelineStage]
    embeddings: List[EmbeddingModel]
    index: List[EmbeddingModel]
    agg_status: str
    agg_details: Dict[str, Any]
    seq: int = 0
