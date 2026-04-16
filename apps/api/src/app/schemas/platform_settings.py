"""
PlatformSettings schemas for API.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


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
    
    # === Global Caps / Rails ===
    abs_max_timeout_s: Optional[int] = Field(None, description="Absolute maximum timeout in seconds")
    abs_max_retries: Optional[int] = Field(None, description="Absolute maximum retry attempts")
    abs_max_steps: Optional[int] = Field(None, description="Absolute maximum agent steps")
    abs_max_plan_steps: Optional[int] = Field(None, description="Absolute maximum planner steps")
    abs_max_concurrency: Optional[int] = Field(None, description="Absolute maximum concurrent operations")
    abs_max_task_runtime_s: Optional[int] = Field(None, description="Absolute maximum task runtime in seconds")
    abs_max_tool_calls_per_step: Optional[int] = Field(None, description="Absolute maximum tool calls per step")

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

    class Config:
        from_attributes = True
