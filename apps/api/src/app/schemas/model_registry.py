"""
Model Registry Pydantic schemas

New architecture schemas for Model table.
Only LLM and Embedding models stored in database.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from enum import Enum


class ModelTypeEnum(str, Enum):
    """Model types"""
    LLM_CHAT = "llm_chat"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    OCR = "ocr"
    ASR = "asr"
    TTS = "tts"


class ModelStatusEnum(str, Enum):
    """Model availability status"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEPRECATED = "deprecated"
    MAINTENANCE = "maintenance"


class HealthStatusEnum(str, Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ModelBase(BaseModel):
    """Base model schema"""
    alias: str = Field(..., min_length=1, max_length=100, description="Unique identifier (e.g. llm.chat.default)")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    type: ModelTypeEnum = Field(..., description="Model type")
    provider: str = Field(..., min_length=1, max_length=50, description="Provider (openai, groq, local, etc.)")
    provider_model_name: str = Field(..., min_length=1, max_length=255, description="Model name at provider")
    base_url: str = Field(..., min_length=1, max_length=500, description="API base URL")
    api_key_ref: Optional[str] = Field(None, max_length=255, description="Reference to secret (not raw key)")
    extra_config: Optional[Dict[str, Any]] = Field(None, description="Provider-specific config (JSON)")
    status: ModelStatusEnum = Field(default=ModelStatusEnum.AVAILABLE, description="Availability status")
    enabled: bool = Field(default=True, description="Is model enabled")
    is_system: bool = Field(default=False, description="System model (cannot be deleted)")
    default_for_type: bool = Field(default=False, description="Default model for this type")
    model_version: Optional[str] = Field(None, max_length=50, description="Model version (for tracking changes)")
    description: Optional[str] = Field(None, description="Model description")

    model_config = ConfigDict(use_enum_values=True)


class ModelCreate(ModelBase):
    """Schema for creating a new model"""
    pass


class ModelUpdate(BaseModel):
    """Schema for updating a model"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    provider: Optional[str] = Field(None, min_length=1, max_length=50)
    provider_model_name: Optional[str] = Field(None, min_length=1, max_length=255)
    base_url: Optional[str] = Field(None, min_length=1, max_length=500)
    api_key_ref: Optional[str] = Field(None, max_length=255)
    extra_config: Optional[Dict[str, Any]] = None
    status: Optional[ModelStatusEnum] = None
    enabled: Optional[bool] = None
    default_for_type: Optional[bool] = None
    model_version: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)


class Model(ModelBase):
    """Schema for model response"""
    id: str
    last_health_check_at: Optional[datetime] = None
    health_status: Optional[HealthStatusEnum] = None
    health_error: Optional[str] = None
    health_latency_ms: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ModelListResponse(BaseModel):
    """Schema for paginated model list"""
    items: List[Model]
    total: int
    page: int
    size: int
    has_more: bool


class HealthCheckRequest(BaseModel):
    """Schema for health check request"""
    force: bool = Field(default=False, description="Force health check even if recently checked")


class HealthCheckResponse(BaseModel):
    """Schema for health check response"""
    model_id: str
    alias: str
    status: HealthStatusEnum
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    checked_at: datetime


# Backward compatibility aliases (will be removed after migration)
ModelRegistry = Model
ModelRegistryBase = ModelBase
ModelRegistryCreate = ModelCreate
ModelRegistryUpdate = ModelUpdate
ModelRegistryListResponse = ModelListResponse
