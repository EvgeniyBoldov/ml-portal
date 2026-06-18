"""RuntimeTurnState — canonical runtime turn DTO.

Single source of truth for runtime turn state. Replaces legacy WorkingMemory.
All planner/stage ports consume this state directly.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.runtime.memory.components import MemoryBundle, MemorySection
from app.runtime.memory.tool_ledger import ToolLedger
from app.runtime.contracts import TaskJournalEntry, TaskJournalNeed, AgentAnswerStatus


# Runtime limits — single source of truth (replaces divergent limits from legacy WorkingMemory)
MAX_RUNTIME_FACTS = 60
MAX_RUNTIME_PLANNER_STEPS = 80
MAX_RUNTIME_RESULTS = 30
MAX_RUNTIME_ACTION_SIGNATURES = 12
MAX_RUNTIME_ITERATION_RESULTS = 80
LOOP_THRESHOLD = 3  # Now configurable via RuntimeBudget.loop_threshold


class RuntimeFact(BaseModel):
    text: str = Field(min_length=1, description="Fact text must be non-empty")
    source: str = "runtime"


class PlannerIterationResult(BaseModel):
    iteration: int = 0
    step_kind: str = ""
    agent_slug: Optional[str] = None
    phase_id: Optional[str] = None
    outcome: str = "unknown"  # success | failed | partial | needs_input | final | aborted
    summary: str = ""
    missing_inputs: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    sufficient_for_phase: bool = False
    retryable: Optional[bool] = None
    error_code: Optional[str] = None
    signature: str = ""


class RuntimeTurnState(BaseModel):
    """Canonical runtime state for one turn."""

    run_id: UUID
    chat_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None

    goal: str = ""
    current_user_query: str = ""
    continuation: Dict[str, Any] = Field(default_factory=dict)
    outline: Optional[Dict[str, Any]] = None
    current_phase_id: Optional[str] = None
    completed_phase_ids: List[str] = Field(default_factory=list)
    blocked_phase_ids: List[str] = Field(default_factory=list)

    memory_bundle: MemoryBundle = Field(default_factory=MemoryBundle)

    planner_steps: List[Dict[str, Any]] = Field(default_factory=list)
    agent_results: List[Dict[str, Any]] = Field(default_factory=list)
    iteration_results: List[PlannerIterationResult] = Field(default_factory=list)
    runtime_facts: List[RuntimeFact] = Field(default_factory=list)
    tool_ledger: ToolLedger = Field(default_factory=ToolLedger)
    open_questions: List[str] = Field(default_factory=list)
    task_journal: List[TaskJournalEntry] = Field(default_factory=list)

    iter_count: int = 0
    used_tool_calls: int = 0
    recent_action_signatures: List[str] = Field(default_factory=list)

    status: str = "running"
    answer_brief: Optional[str] = None
    final_answer: Optional[str] = None
    final_error: Optional[str] = None

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
        continuation: Optional[Dict[str, Any]] = None,
    ) -> "RuntimeTurnState":
        return cls(
            run_id=run_id,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            goal=goal,
            current_user_query=current_user_query,
            memory_bundle=memory_bundle,
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

    def add_planner_step(self, step: Dict[str, Any]) -> None:
        self.planner_steps.append(dict(step or {}))
        if len(self.planner_steps) > MAX_RUNTIME_PLANNER_STEPS:
            self.planner_steps = self.planner_steps[-MAX_RUNTIME_PLANNER_STEPS:]

        if str((step or {}).get("kind") or "") == "call_agent":
            signature = self._step_signature(step)
            self.recent_action_signatures.append(signature)
            if len(self.recent_action_signatures) > MAX_RUNTIME_ACTION_SIGNATURES:
                self.recent_action_signatures = self.recent_action_signatures[-MAX_RUNTIME_ACTION_SIGNATURES:]

    def add_agent_result(self, result: Dict[str, Any]) -> None:
        self.agent_results.append(dict(result or {}))
        if len(self.agent_results) > MAX_RUNTIME_RESULTS:
            self.agent_results = self.agent_results[-MAX_RUNTIME_RESULTS:]

    def add_iteration_result(self, result: Dict[str, Any]) -> None:
        entry = PlannerIterationResult.model_validate(result or {})
        self.iteration_results.append(entry)
        if len(self.iteration_results) > MAX_RUNTIME_ITERATION_RESULTS:
            self.iteration_results = self.iteration_results[-MAX_RUNTIME_ITERATION_RESULTS:]

    def latest_iteration_result(self) -> Optional[PlannerIterationResult]:
        if not self.iteration_results:
            return None
        return self.iteration_results[-1]

    def detect_loop(self, threshold: Optional[int] = None) -> bool:
        effective = threshold if threshold is not None else LOOP_THRESHOLD
        if len(self.recent_action_signatures) < effective:
            return False
        tail = self.recent_action_signatures[-effective:]
        return len(set(tail)) == 1

    def can_finalize(self) -> bool:
        """True when no must_do phase remains unfinished AND no active tasks block finalization."""
        # Legacy phase guard
        if self.outline:
            for phase in self.outline.get("phases", []):
                if not phase.get("must_do", True):
                    continue
                if phase.get("allow_final_after"):
                    continue
                if phase.get("phase_id") not in self.completed_phase_ids:
                    return False
        # Task journal guard: cannot finalize while there are pending/in_progress/paused_need tasks
        for task in self.task_journal:
            if task.status in ("pending", "in_progress", "paused_need"):
                return False
        return True

    def record_operation_call(
        self,
        *,
        operation: str,
        call_id: str,
        arguments: Dict[str, Any],
        agent_slug: Optional[str],
        phase_id: Optional[str],
    ) -> None:
        self.tool_ledger.register_call(
            operation=operation,
            call_id=call_id,
            arguments=arguments,
            iteration=self.iter_count,
            agent_slug=agent_slug,
            phase_id=phase_id,
        )
        self.used_tool_calls += 1

    def record_operation_result(
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

    def get_or_create_task(self, task_id: str, **defaults: Any) -> TaskJournalEntry:
        for t in self.task_journal:
            if t.task_id == task_id:
                return t
        entry = TaskJournalEntry(task_id=task_id, **defaults)
        self.task_journal.append(entry)
        return entry

    def find_task_by_agent_and_phase(
        self,
        agent_slug: str,
        phase_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[TaskJournalEntry]:
        for t in reversed(self.task_journal):
            if t.assigned_agent != agent_slug:
                continue
            if phase_id is not None and t.task_id != str(phase_id or ""):
                continue
            if status is not None and t.status != status:
                continue
            return t
        return None

    def pending_needs(self) -> List[TaskJournalNeed]:
        result: List[TaskJournalNeed] = []
        for t in self.task_journal:
            for n in t.needs:
                if n.status == "pending":
                    result.append(n)
        return result

    def unresolved_tasks(self) -> List[TaskJournalEntry]:
        return [t for t in self.task_journal if t.status in ("pending", "in_progress", "paused_need")]

    def all_needs_resolved(self, task: TaskJournalEntry) -> bool:
        return all(n.status == "resolved" for n in task.needs)

    def planner_snapshot(self, *, max_items: int = 10) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "iter_count": self.iter_count,
            "continuation": dict(self.continuation or {}),
            "facts": [item.text for item in self.runtime_facts[-max_items:]],
            "agent_results": list(self.agent_results[-max_items:]),
            "iteration_results": [item.model_dump() for item in self.iteration_results[-max_items:]],
            "open_questions": list(self.open_questions[-max_items:]),
            "recent_actions": list(self.recent_action_signatures[-max_items:]),
            "task_journal": [t.model_dump() for t in self.task_journal[-max_items:]],
            "recent_tool_calls": self.tool_ledger.compact_view(max_items=max_items),
            "answer_brief": (self.answer_brief or "")[:300],
        }

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
            "goal": self.goal,
            "current_user_query": self.current_user_query,
            "continuation": dict(self.continuation or {}),
            "status": self.status,
            "iter_count": self.iter_count,
            "used_tool_calls": self.used_tool_calls,
            "answer_brief": (self.answer_brief or "")[:300],
            "final_answer": (self.final_answer or "")[:300],
            "final_error": (self.final_error or "")[:300],
            "planner_steps": len(self.planner_steps),
            "task_journal": len(self.task_journal),
            "agent_results": len(self.agent_results),
            "iteration_results": len(self.iteration_results),
            "runtime_facts": len(self.runtime_facts),
            "open_questions": list(self.open_questions[-5:]),
            "tool_ledger": self.tool_ledger.compact_view(max_items=8),
            "memory_bundle": self.memory_bundle.compact_view(),
        }

    @staticmethod
    def _step_signature(step: Dict[str, Any]) -> str:
        kind = str((step or {}).get("kind") or "-")
        agent_slug = str((step or {}).get("agent_slug") or "-")
        phase_id = str((step or {}).get("phase_id") or "-")
        # Include a stable hash of the full query to distinguish different calls
        # to the same agent while keeping signature length fixed.
        agent_input = (step or {}).get("agent_input") or {}
        query = " ".join(str(agent_input.get("query") or "").split())
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()[:12] if query else "-"
        question = " ".join(str((step or {}).get("question") or "").split())
        question_hash = hashlib.md5(question.encode("utf-8")).hexdigest()[:12] if question else "-"
        payload = f"{kind}|{agent_slug}|{phase_id}|{query_hash}|{question_hash}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]
    model_config = ConfigDict(arbitrary_types_allowed=True)
