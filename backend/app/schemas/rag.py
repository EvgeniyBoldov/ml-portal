from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date

class RagSearchRequest(BaseModel):
    query: Optional[str] = Field(None)
    top_k: Optional[int] = Field(None)
    filters: Optional[Dict[str, Any]] = Field(None)
    with_snippets: Optional[bool] = Field(None)

class RagUploadRequest(BaseModel):
    url: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)

class RagDocument(BaseModel):
    id: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    date_upload: Optional[datetime] = Field(None)
    url_file: Optional[str] = Field(None)
    url_canonical_file: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)
    progress: Optional[float] = Field(None)
