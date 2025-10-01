"""
Analyze schemas for API v1
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

class AnalyzeRunRequest(BaseModel):
    """Request schema for analyze run"""
    prompt: str = Field(..., min_length=1, max_length=1000, description="Analysis prompt")
    model: Optional[str] = Field(None, description="Model to use for analysis")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Temperature for generation")
    max_tokens: Optional[int] = Field(1000, ge=1, le=4000, description="Maximum tokens to generate")

class AnalyzeRunResponse(BaseModel):
    """Response schema for analyze run"""
    job_id: str = Field(..., description="Job ID for tracking")
    status: str = Field(..., description="Job status")
    created_at: datetime = Field(..., description="Job creation time")

class AnalyzeStatusResponse(BaseModel):
    """Response schema for analyze status"""
    analyze_id: str = Field(..., description="Analysis ID")
    status: str = Field(..., description="Job status")
    created_at: Optional[datetime] = Field(None, description="Job creation time")
    updated_at: Optional[datetime] = Field(None, description="Job last update time")
    result: Optional[Dict[str, Any]] = Field(None, description="Analysis result")
    error: Optional[str] = Field(None, description="Error message if failed")
    artifact: Optional[Dict[str, Any]] = Field(None, description="Artifact information")

class AnalyzeUploadRequest(BaseModel):
    """Request schema for analyze upload"""
    name: str = Field(..., min_length=1, max_length=255, description="Document name")
    mime: str = Field(..., description="MIME type")
    size: int = Field(..., gt=0, le=50*1024*1024, description="File size in bytes")

class AnalyzeUploadResponse(BaseModel):
    """Response schema for analyze upload"""
    analyze_id: str = Field(..., description="Analysis ID")
    upload: Dict[str, Any] = Field(..., description="Upload information")