"""
PlatformSettings schemas for API.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class PlatformSettingsBase(BaseModel):
    """Base schema for PlatformSettings."""
    
    # === Global Policy Settings ===
    policies_text: Optional[str] = Field(None, description="Policy text for planner/executor (markdown)")
    
    # Policy gates - global safety flags
    require_confirmation_for_write: Optional[bool] = Field(False, description="Require confirmation for write operations")
    require_confirmation_for_destructive: Optional[bool] = Field(False, description="Require confirmation for destructive operations")
    forbid_destructive: Optional[bool] = Field(False, description="Forbid destructive operations globally")
    forbid_write_in_prod: Optional[bool] = Field(False, description="Forbid write operations in production")
    require_backup_before_write: Optional[bool] = Field(False, description="Require backup before write operations")
    
    # === Chat File Upload ===
    chat_upload_max_bytes: Optional[int] = Field(None, description="Max upload size for chat attachments in bytes")
    chat_upload_allowed_extensions: Optional[str] = Field(
        None,
        description="Comma-separated allowed file extensions for chat uploads (e.g. txt,md,pdf,docx,xlsx,csv)",
    )


class PlatformSettingsCreate(PlatformSettingsBase):
    """Schema for creating PlatformSettings."""
    pass


class PlatformSettingsUpdate(PlatformSettingsBase):
    """Schema for updating PlatformSettings."""
    pass


class PlatformSettingsResponse(PlatformSettingsBase):
    """Schema for PlatformSettings response."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
