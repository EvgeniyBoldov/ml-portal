"""RuntimeTurnState — canonical runtime turn DTO.

Single source of truth for runtime turn state. Replaces legacy WorkingMemory.
All planner/stage ports consume this state directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.runtime.memory.components import MemoryBundle, MemorySection
from app.runtime.memory.tool_ledger import ToolLedger
from app.runtime.project_memory_candidates import ProjectMemoryCandidate
from app.runtime.contracts import (
    AttachmentContext,
    ExecutionMode,
)


# Runtime limits — single source of truth (replaces divergent limits from legacy WorkingMemory)
MAX_RUNTIME_FACTS = 60
MAX_RUNTIME_RESULTS = 30


class RuntimeFact(BaseModel):
    text: str = Field(min_length=1, description="Fact text must be non-empty")
    source: str = "runtime"


class RuntimeTurnState(BaseModel):
    """Canonical runtime state for one turn."""

    run_id: UUID
    chat_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    execution_mode: ExecutionMode = ExecutionMode.NORMAL

    goal: str = ""
    current_user_query: str = ""
    attachment_contexts: List[AttachmentContext] = Field(default_factory=list)
    continuation: Dict[str, Any] = Field(default_factory=dict)
    memory_bundle: MemoryBundle = Field(default_factory=MemoryBundle)

    # Runtime-owned projection of logical task results for memory writeback.
    task_results: List[Dict[str, Any]] = Field(default_factory=list)
    runtime_facts: List[RuntimeFact] = Field(default_factory=list)
    project_memory_candidates: List[ProjectMemoryCandidate] = Field(default_factory=list)
    tool_ledger: ToolLedger = Field(default_factory=ToolLedger)
    used_tool_calls: int = 0

    status: str = "running"
    final_answer: Optional[str] = None
    final_error: Optional[str] = None
    deleted_artifact_ids: List[str] = Field(default_factory=list)

    @field_validator("memory_bundle", mode="before")
    @classmethod
    def _coerce_memory_bundle(cls, value: Any) -> MemoryBundle:
        if isinstance(value, MemoryBundle):
            return value
        if isinstance(value, dict):
            sections = value.get("sections") if isinstance(value.get("sections"), list) else []
            bundle = MemoryBundle()
            bundle.total_budget_used_chars = int(value.get("total_budget_used_chars") or 0)
            bundle.diagnostics = dict(value.get("diagnostics") or {})
            for item in sections:
                if not isinstance(item, dict):
                    continue
                bundle.sections.append(
                    MemorySection(
                        name=str(item.get("name") or "section"),
                        priority=int(item.get("priority") or 100),
                        omitted_count=int(item.get("omitted_count") or 0),
                        budget_used_chars=int(item.get("budget_used_chars") or 0),
                        selection_reason=str(item.get("selection_reason") or ""),
                        redaction_level=str(item.get("redaction_level") or "safe"),
                        status=str(item.get("status") or "ok"),
                        error=item.get("error"),
                    )
                )
            return bundle
        return MemoryBundle()

    @field_serializer("memory_bundle")
    def _serialize_memory_bundle(self, value: MemoryBundle) -> Dict[str, Any]:
        return value.compact_view()

    @classmethod
    def from_seed(
        cls,
        *,
        run_id: UUID,
        chat_id: Optional[UUID],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
        goal: str,
        current_user_query: str,
        memory_bundle: MemoryBundle,
        attachment_contexts: Optional[List[AttachmentContext]] = None,
        continuation: Optional[Dict[str, Any]] = None,
    ) -> "RuntimeTurnState":
        return cls(
            run_id=run_id,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            execution_mode=ExecutionMode.NORMAL,
            goal=goal,
            current_user_query=current_user_query,
            memory_bundle=memory_bundle,
            attachment_contexts=list(attachment_contexts or []),
            continuation=dict(continuation or {}),
        )

    @staticmethod
    def _normalize_fact(text: str) -> str:
        """Normalize fact text for deduplication (lowercase + collapse whitespace)."""
        return " ".join(text.lower().split())

    def add_runtime_fact(self, text: str, *, source: str = "runtime") -> None:
        text = (text or "").strip()
        if not text:
            return
        normalized = self._normalize_fact(text)
        if any(self._normalize_fact(item.text) == normalized for item in self.runtime_facts):
            return
        self.runtime_facts.append(RuntimeFact(text=text, source=source))
        if len(self.runtime_facts) > MAX_RUNTIME_FACTS:
            self.runtime_facts = self.runtime_facts[-MAX_RUNTIME_FACTS:]

    def add_task_result(self, result: Dict[str, Any]) -> None:
        self.task_results.append(dict(result or {}))
        if len(self.task_results) > MAX_RUNTIME_RESULTS:
            self.task_results = self.task_results[-MAX_RUNTIME_RESULTS:]

    def record_tool_call(
        self,
        *,
        tool: str,
        call_id: str,
        arguments: Dict[str, Any],
        agent_slug: Optional[str],
        phase_id: Optional[str],
    ) -> None:
        self.tool_ledger.register_call(
            operation=tool,
            call_id=call_id,
            arguments=arguments,
            iteration=0,
            agent_slug=agent_slug,
            phase_id=phase_id,
        )
        self.used_tool_calls += 1

    def record_tool_result(
        self,
        *,
        call_id: str,
        success: bool,
        data: Any,
    ) -> None:
        self.tool_ledger.register_result(
            call_id=call_id,
            success=success,
            data=data,
        )

    def mark_artifact_deleted(self, artifact_id: str) -> None:
        artifact_id = str(artifact_id or "").strip()
        if artifact_id and artifact_id not in self.deleted_artifact_ids:
            self.deleted_artifact_ids.append(artifact_id)

    def compact_view(self) -> Dict[str, Any]:
        """Return compact diagnostics view with bounded size.

        NOTE(4.2): All nested views use max_items limits to prevent unbounded
        growth. Final strings are truncated to 300 chars. Total payload is
        typically < 5KB even for long turns.
        """
        return {
            "run_id": str(self.run_id),
            "chat_id": str(self.chat_id) if self.chat_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "execution_mode": self.execution_mode.value,
            "goal": self.goal,
            "current_user_query": self.current_user_query,
            "continuation": dict(self.continuation or {}),
            "attachments": [item.model_dump(mode="json") for item in self.attachment_contexts[-5:]],
            "status": self.status,
            "used_tool_calls": self.used_tool_calls,
            "final_answer": (self.final_answer or "")[:300],
            "final_error": (self.final_error or "")[:300],
            "task_results": len(self.task_results),
            "runtime_facts": len(self.runtime_facts),
            "tool_ledger": self.tool_ledger.compact_view(max_items=8),
            "memory_bundle": self.memory_bundle.compact_view(),
        }

    model_config = ConfigDict(arbitrary_types_allowed=True)
