"""Typed working context with stable evidence identities across runtime roles."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    owner: str = "turn_preflight"
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class RunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: int = 1
    revision: int = 0
    original_request: str = ""
    goal: str = ""
    constraints: list[str] = Field(default_factory=list)
    answer_requirements: str = ""
    chat_snapshot: dict[str, Any] = Field(default_factory=dict)
    recent_dialogue: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[RunEvidence] = Field(default_factory=list)
    available_artifact_ids: list[str] = Field(default_factory=list)
    artifact_descriptions: dict[str, str] = Field(default_factory=dict)
    synthesis_message: str | None = None
    delivered_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    generated_artifacts: list[dict[str, Any]] = Field(default_factory=list)

    def add_evidence(self, tool: str, arguments: dict[str, Any], data: dict[str, Any], *, owner: str = "turn_preflight") -> str:
        identity = hashlib.sha256(json.dumps([owner, tool, arguments, data], sort_keys=True, default=str).encode()).hexdigest()
        if not any(item.id == identity for item in self.evidence):
            self.evidence.append(RunEvidence(id=identity, owner=owner, tool=tool, arguments=arguments, data=data))
        return identity

    def projection(self, *, scope_keys: list[str] | None = None, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        value = self.model_dump(mode="json")
        if evidence_refs is not None:
            value["evidence"] = [item for item in value["evidence"] if item["id"] in evidence_refs]
        if scope_keys is not None:
            for evidence in value["evidence"]:
                if evidence["tool"] == "memory.search" and isinstance(evidence["data"].get("groups"), list):
                    evidence["data"]["groups"] = [group for group in evidence["data"]["groups"]
                        if group.get("scope_slug") in scope_keys]
                    evidence["data"]["group_count"] = len(evidence["data"]["groups"])
                    evidence["data"]["partial"] = any(not group.get("success", True) for group in evidence["data"]["groups"])
        return value
