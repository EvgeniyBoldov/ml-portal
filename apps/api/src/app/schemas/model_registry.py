"""
Model Registry Pydantic schemas
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class ModelRegistryBase(BaseModel):
    """Base model registry schema"""
    model: str = Field(..., description="Unique model identifier from manifest")
    version: str = Field(..., description="Model version")
    modality: str = Field(..., description="Model modality: text|image|layout|table|rerank")
    state: str = Field(default="active", description="Model state: active|archived|retired|disabled")
    vector_dim: Optional[int] = Field(None, description="Vector dimension for embedding models")
    path: str = Field(..., description="Full path to model directory")
    is_global: bool = Field(
        default=False,
        alias="global",
        serialization_alias="global",
        description="Mark as global model for modality",
    )
    notes: Optional[str] = Field(None, description="Additional notes about the model")

    model_config = ConfigDict(populate_by_name=True)


class ModelRegistryCreate(ModelRegistryBase):
    """Schema for creating a new model registry entry"""
    pass


class ModelRegistryUpdate(BaseModel):
    """Schema for updating a model registry entry"""
    state: Optional[str] = Field(None, description="Model state: active|archived|retired|disabled")
    is_global: Optional[bool] = Field(
        None,
        alias="global",
        serialization_alias="global",
        description="Mark as global model for modality",
    )
    notes: Optional[str] = Field(None, description="Additional notes about the model")

    model_config = ConfigDict(populate_by_name=True)


class ModelRegistry(ModelRegistryBase):
    """Schema for model registry response"""
    id: str
    used_by_tenants: int = Field(default=0, description="Number of tenants using this model")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ModelRegistryListResponse(BaseModel):
    """Schema for paginated model registry list"""
    items: List[ModelRegistry]
    total: int
    page: int
    size: int
    has_more: bool


class ScanResult(BaseModel):
    """Schema for model directory scan results"""
    added: List[str] = Field(default_factory=list, description="Newly added models")
    updated: List[str] = Field(default_factory=list, description="Updated models")
    disabled: List[str] = Field(default_factory=list, description="Disabled models (missing from FS)")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Scan errors")


class RetireRequest(BaseModel):
    """Schema for model retirement request"""
    drop_vectors: bool = Field(default=False, description="Drop vector collections")
    remove_from_tenants: bool = Field(default=False, description="Remove from tenant profiles")


class RetireResponse(BaseModel):
    """Schema for model retirement response"""
    success: bool
    affected_tenants: List[str] = Field(default_factory=list, description="Affected tenant IDs")
    message: str
