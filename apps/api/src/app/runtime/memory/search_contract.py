"""Canonical memory-search arguments shared by agents and root routing."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HippoMemorySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=12)


class MemorySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)
    team_keys: list[str] | None = Field(default=None, max_length=30, description="All team_keys from execution_context. Omit to use them automatically. Cannot replace or clear context teams.")
    project_keys: list[str] | None = Field(default=None, max_length=30, description="Choose only projects from execution_context. Omit to use focused projects; [] means outside projects; [project.all] means only common project rules. Each concrete project is searched independently.")
    kinds: list[Literal["description", "relationship", "rule", "constraint", "procedure", "decision", "fact"]] = Field(
        default_factory=list,
        description="Optional item types. Omit or [] to search all types. project/team/global/glossary are scopes, never kinds.",
    )
    entity_ids: list[str] = Field(default_factory=list)
    direction: str | None = None
    fact_subject: str | None = Field(default=None, max_length=200)
    scopes: list[Literal["glossary", "project", "team", "global", "user", "tenant"]] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=12)

