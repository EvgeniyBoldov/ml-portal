"""Turn-scoped contracts for explicit project-memory proposals."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ProjectMemoryCandidate(BaseModel):
    """A proposal retained in runtime state until async memory finalization."""

    project_key: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=2000)
    evidence_call_ids: List[str] = Field(min_length=1, max_length=8)
    aliases: List[str] = Field(default_factory=list, max_length=12)
