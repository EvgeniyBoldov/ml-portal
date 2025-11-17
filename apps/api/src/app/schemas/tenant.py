# Tenant schemas and models

from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import uuid

class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tenant name")
    description: Optional[str] = Field(None, max_length=500, description="Tenant description")
    is_active: bool = Field(True, description="Whether tenant is active")
    # Model-related fields (requests use extra_embed_model, responses provide computed lists)
    extra_embed_model: Optional[str] = Field(None, description="An optional extra embedding model (besides global)")
    ocr: bool = Field(False, description="Enable OCR processing")
    layout: bool = Field(False, description="Enable layout analysis")
    
    model_config = ConfigDict(extra='ignore')

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    extra_embed_model: Optional[str] = Field(None, description="An optional extra embedding model (besides global)")
    ocr: Optional[bool] = Field(None, description="Enable OCR processing")
    layout: Optional[bool] = Field(None, description="Enable layout analysis")
    
    model_config = ConfigDict(extra='ignore')

class Tenant(TenantBase):
    embed_models: List[str] = Field(default_factory=list, description="Resolved embedding models (global + optional extra)")
    rerank_model: Optional[str] = Field(None, description="Resolved global rerank model")
    id: str = Field(..., description="Tenant ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True, extra='ignore')

class TenantListResponse(BaseModel):
    items: list[Tenant]
    total: int
    page: int
    size: int
    has_more: bool
    
    model_config = ConfigDict(extra='ignore')
