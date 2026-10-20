"""Typed working context with stable evidence identities across runtime roles."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResolvedReference(BaseModel):
    """Preflight's interpretation of a conversational reference, with provenance."""
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    source_message_ids: list[str] = Field(default_factory=list)


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
    task_brief: dict[str, Any] = Field(default_factory=dict)
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

    def projection(self, *, scope_keys: list[str] | None = None, evidence_refs: list[str] | None = None,
                   message_refs: list[str] | None = None) -> dict[str, Any]:
        """Project the task handoff, never replay the persisted conversation.

        Only preflight sees the automatic dialogue tail/snapshot. Other roles
        receive selected material as data, not as their own assistant messages.
        """
        selected_evidence = set(self.task_brief.get("evidence_refs") or []) if evidence_refs is None else set(evidence_refs)
        selected_messages = set(self.task_brief.get("message_refs") or []) if message_refs is None else set(message_refs)
        source_evidence: list[dict[str, Any]] = []
        conversation: dict[str, dict[str, Any]] = {}
        known_messages = {str(item["message_id"]): item for item in self.recent_dialogue if item.get("message_id")}
        known_evidence = {item.id for item in self.evidence}
        for item in self.evidence:
            if item.tool == "chat.history.read":
                messages = item.data.get("messages") or []
                for message in messages:
                    if isinstance(message, dict) and message.get("message_id"):
                        key = str(message["message_id"])
                        previous = known_messages.get(key)
                        if previous is None or previous.get("truncated") or not message.get("truncated"):
                            known_messages[key] = {**message, "evidence_id": item.id}
                        if item.id in selected_evidence:
                            selected_messages.add(key)
            elif item.id in selected_evidence:
                source_evidence.append(item.model_dump(mode="json"))
        for key, item in known_messages.items():
            if key in selected_messages:
                conversation[key] = {name: item[name] for name in (
                    "message_id", "role", "content", "truncated", "created_at", "source_run_id", "status", "evidence_id",
                ) if name in item}
        value: dict[str, Any] = {
            "original_request": self.original_request, "goal": self.goal,
            "constraints": list(self.constraints), "answer_requirements": self.answer_requirements,
            "resolved_references": self.task_brief.get("resolved_references") or [],
            "uncertainties": self.task_brief.get("uncertainties") or [],
            "evidence": source_evidence,
            "conversation_materials": list(conversation.values()),
        }
        missing = sorted((selected_evidence - known_evidence) | (selected_messages - known_messages.keys()))
        if missing:
            value["unavailable_material_refs"] = missing
        if scope_keys is not None:
            for evidence in value["evidence"]:
                if evidence["tool"] == "memory.search" and isinstance(evidence["data"].get("groups"), list):
                    evidence["data"]["groups"] = [group for group in evidence["data"]["groups"]
                        if group.get("scope_slug") in scope_keys]
                    evidence["data"]["group_count"] = len(evidence["data"]["groups"])
                    evidence["data"]["partial"] = any(not group.get("success", True) for group in evidence["data"]["groups"])
        return value
