from __future__ import annotations

from typing import Any, Optional, List, Dict

from pydantic import BaseModel, ConfigDict


class StatusNode(BaseModel):
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str
    model_version: Optional[str] = None

    model_config = ConfigDict(protected_namespaces=())


class PipelineStage(BaseModel):
    key: str
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str


class EmbeddingModel(BaseModel):
    model: str
    version: Optional[str] = None
    status: str
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str


class StageControl(BaseModel):
    stage: str
    node_type: str
    status: str
    retry_supported: bool
    can_retry: bool
    can_stop: bool


class IngestPolicyResponse(BaseModel):
    archived: bool
    start_allowed: bool
    start_reason: Optional[str] = None
    active_stages: List[str]
    retryable_stages: List[str]
    stoppable_stages: List[str]
    controls: List[StageControl]


class StatusGraphResponse(BaseModel):
    doc_id: str
    pipeline: List[PipelineStage]
    embeddings: List[EmbeddingModel]
    index: List[EmbeddingModel]
    agg_status: str
    agg_details: Dict[str, Any]
    ingest_policy: Optional[IngestPolicyResponse] = None
    seq: int = 0
