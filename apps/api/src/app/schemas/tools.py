from typing import Any, Dict, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ToolBase(BaseModel):
    slug: str = Field(..., description="Unique identifier", example="netbox.get_device")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    type: str = Field("api", description="Tool type: api, function, database")
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema for input arguments")
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = {}
    is_active: bool = True


class ToolCreate(ToolBase):
    pass


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ToolResponse(ToolBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
