"""
Schemas for Tool Releases API
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# TOOL BACKEND RELEASE (read-only, from code)
# ─────────────────────────────────────────────────────────────────────────────

class ToolBackendReleaseResponse(BaseModel):
    """Backend release response (version from code)"""
    id: UUID
    tool_id: UUID
    version: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    method_name: str
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    schema_hash: Optional[str] = None
    worker_build_id: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ToolBackendReleaseListItem(BaseModel):
    """Backend release list item"""
    id: UUID
    version: str
    description: Optional[str] = None
    deprecated: bool = False
    schema_hash: Optional[str] = None
    worker_build_id: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    synced_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASE (CRUD, for agents)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.splitlines()
    else:
        raw_items = []

    result: list[str] = []
    for item in raw_items:
        normalized = _normalize_text(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


class ToolSemanticProfileSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    when_to_use: str = ""
    limitations: str = ""
    examples: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        payload = value if isinstance(value, dict) else {}
        return {
            "summary": _normalize_text(payload.get("summary") or payload.get("description")),
            "when_to_use": _normalize_text(payload.get("when_to_use")),
            "limitations": _normalize_text(payload.get("limitations")),
            "examples": _normalize_str_list(payload.get("examples")),
        }


class ToolPolicyHintsSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    sensitive_inputs: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        payload = value if isinstance(value, dict) else {}
        return {
            "dos": _normalize_str_list(payload.get("dos")),
            "donts": _normalize_str_list(payload.get("donts")),
            "guardrails": _normalize_str_list(payload.get("guardrails")),
            "sensitive_inputs": _normalize_str_list(payload.get("sensitive_inputs")),
        }


class ToolReleaseCreate(BaseModel):
    """Create tool release request"""
    backend_release_id: Optional[UUID] = Field(None, description="Backend release to use (optional for draft)")
    from_release_id: Optional[UUID] = Field(None, description="Parent release to inherit meta-fields from")
    semantic_profile: Optional[ToolSemanticProfileSchema] = Field(
        default=None,
        description="Human-readable profile for LLM usage",
    )
    policy_hints: Optional[ToolPolicyHintsSchema] = Field(
        default=None,
        description="Safety and usage hints",
    )


class ToolReleaseUpdate(BaseModel):
    """Update tool release request (only draft)"""
    backend_release_id: Optional[UUID] = Field(None, description="Backend release to use")
    semantic_profile: Optional[ToolSemanticProfileSchema] = None
    policy_hints: Optional[ToolPolicyHintsSchema] = None


class ToolReleaseResponse(BaseModel):
    """Tool release response"""
    id: UUID
    tool_id: UUID
    version: int
    backend_release_id: Optional[UUID] = None
    status: str
    semantic_profile: dict[str, Any] = Field(default_factory=dict)
    policy_hints: dict[str, Any] = Field(default_factory=dict)
    # Meta
    meta_hash: Optional[str] = None
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Nested backend release info (full, with schemas)
    backend_release: Optional["ToolBackendReleaseResponse"] = None

    class Config:
        from_attributes = True


class ToolReleaseListItem(BaseModel):
    """Tool release list item"""
    id: UUID
    version: int
    status: str
    backend_release_id: Optional[UUID] = None
    backend_version: Optional[str] = None
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DIFF
# ─────────────────────────────────────────────────────────────────────────────

class SchemaDiffField(BaseModel):
    """A field in a schema diff"""
    name: str
    type: str = "unknown"
    required: bool = False
    description: str = ""


class SchemaDiffChangedField(BaseModel):
    """A field whose type changed"""
    name: str
    old_type: str
    new_type: str


class SchemaDiffResponse(BaseModel):
    """Schema diff between two backend releases"""
    added_fields: List[SchemaDiffField] = []
    removed_fields: List[SchemaDiffField] = []
    changed_fields: List[SchemaDiffChangedField] = []
