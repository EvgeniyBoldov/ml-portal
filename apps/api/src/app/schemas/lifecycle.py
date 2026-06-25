from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


LifecycleKind = Literal["tenant", "user", "collection", "agent", "rbac_rule"]
LifecycleMode = Literal["soft", "hard", "restore"]


class DependencyEntity(BaseModel):
    uuid: str
    name: str
    url: str | None = None


class DependencyEntry(BaseModel):
    resource_type: str
    count: int = Field(ge=0)
    action: str
    will_be: Literal["cascade_deprecated", "cascade_deleted", "migrated", "set_null", "blocker", "already_deprecated"] = "cascade_deleted"
    entities: list[DependencyEntity] = Field(default_factory=list, max_length=5)
    migration_target: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DependencyGraphResponse(BaseModel):
    kind: LifecycleKind
    entity_id: str
    dependencies: list[DependencyEntry]


class LifecycleReportResponse(BaseModel):
    kind: LifecycleKind
    entity_id: str
    mode: LifecycleMode
    lifecycle_status: str
    details: dict[str, Any] = Field(default_factory=dict)
    migrated: dict[str, int] = Field(default_factory=dict)
    cascaded: dict[str, int] = Field(default_factory=dict)
    set_null: dict[str, int] = Field(default_factory=dict)
    rbac_rules_removed: int = 0
    renamed: list[dict[str, str]] = Field(default_factory=list)
    restored: dict[str, int] = Field(default_factory=dict)
