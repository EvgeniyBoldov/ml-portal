from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RawEventRefResponse(BaseModel):
    id: str
    raw_type: str
    raw: Dict[str, Any] = {}


class SemanticEventResponse(BaseModel):
    id: str
    raw_type: str
    category: str
    title: str
    summary: str
    status: str
    phase: str
    iteration: int
    started_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    decision: Optional[Dict[str, Any]] = None
    budget: Optional[Dict[str, Any]] = None
    refs: Optional[Dict[str, Any]] = None
    raw: RawEventRefResponse


class TraceIterationResponse(BaseModel):
    index: int
    events: List[SemanticEventResponse] = []


class RunTraceResponse(BaseModel):
    iterations: List[TraceIterationResponse] = []
    total_events: int = 0

