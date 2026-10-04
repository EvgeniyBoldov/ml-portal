"""Canonical memory-search arguments shared by agents and root routing."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemorySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)
    team_keys: list[str] | None = Field(default=None, max_length=30, description="All team_keys from execution_context. Omit to use them automatically. Cannot replace or clear context teams.")
    project_keys: list[str] | None = Field(default=None, max_length=30, description="Choose only projects from execution_context. Omit to use focused projects; [] means outside projects; [project.all] means only common project rules. Each concrete project is searched independently.")
    kinds: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    direction: str | None = None
    fact_subject: str | None = Field(default=None, max_length=200)
    scopes: list[Literal["glossary", "project", "team", "global", "user", "tenant"]] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=12)

