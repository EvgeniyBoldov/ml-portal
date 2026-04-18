from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OrchestrationState(BaseModel):
    """Canonical orchestration state shared across runtime stages."""

    run_id: Optional[str] = None
    chat_id: Optional[str] = None
    tenant_id: Optional[str] = None
    request_text: Optional[str] = None
    goal: Optional[str] = None
    intent_type: Optional[str] = None
    current_phase_id: Optional[str] = None
    current_agent_slug: Optional[str] = None
    open_questions: List[str] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    completed_phase_ids: List[str] = Field(default_factory=list)
    run_status: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
