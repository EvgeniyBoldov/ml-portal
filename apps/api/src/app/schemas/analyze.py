from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date

class AnalyzeRequest(BaseModel):
    source: Optional[Dict[str, Any]] = Field(None)
    pipeline: Optional[Dict[str, Any]] = Field(None)
    language: Optional[str] = Field(None)
    priority: Optional[Literal['low', 'normal', 'high']] = Field(None)
    idempotency_key: Optional[str] = Field(None)

class AnalyzeResult(BaseModel):
    id: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    progress: Optional[float] = Field(None)
    result: Optional[Dict[str, Any]] = Field(None)
    artifacts: Optional[Dict[str, Any]] = Field(None)
