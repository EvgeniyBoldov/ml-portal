"""
WorkingMemory — single source of truth for runtime state.

Replaces the three overlapping stores that existed before:
    * ExecutionMemory (runtime facts/outline/agent_results)
    * OrchestrationState (run_status/phase/intent) — was a JSON blob inside ExecutionMemory
    * RunContextCompact (in-memory planner facts) — was parallel to ExecutionMemory

Now everything lives here. Persisted into `execution_memories` table via
WorkingMemoryRepository. Bounded collections prevent unbounded growth
across many-step runs.

Design principles:
    * Pure data container (no IO)
    * All mutations are explicit methods (no setattr elsewhere)
    * JSON round-trippable (model_dump/model_validate)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


MAX_FACTS = 40
MAX_AGENT_RESULTS = 20
MAX_PLANNER_STEPS = 60
MAX_RECENT_SIGNATURES = 10
MAX_RECENT_MESSAGES = 12
LOOP_THRESHOLD = 3


class Fact(BaseModel):
    """Atomic evidence collected during a run."""

    text: str = Field(..., min_length=1)
    source: str = "planner"             # agent slug or 'planner' / 'user' / 'system'
    phase_id: Optional[str] = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResult(BaseModel):
    """Summary of a sub-agent invocation, for planner & synthesis."""

    agent_slug: str
    summary: str = ""
    facts: List[str] = Field(default_factory=list)
    phase_id: Optional[str] = None
    iteration: int = 0
    success: bool = True
    error: Optional[str] = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlannerStepRecord(BaseModel):
    """One emitted planner decision, kept bounded for loop detection & trace."""

    iteration: int
    kind: str
    agent_slug: Optional[str] = None
    phase_id: Optional[str] = None
    rationale: str = ""
    signature: str = ""
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessageRef(BaseModel):
    """Lightweight pointer to a chat message — used in cross-turn memory."""

    message_id: str
    role: str
    preview: str = ""
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkingMemory(BaseModel):
    """Canonical runtime state. Persisted after every mutation of significance."""

    # identity
    run_id: UUID
    chat_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None

    # goal / intent
    goal: str = ""
    question: str = ""
    intent: Optional[str] = None                   # triage intent value
    status: str = "running"                        # running / waiting_input / completed / failed / ...

    # short-term context (cross-turn)
    dialogue_summary: Optional[str] = None
    recent_messages: List[ChatMessageRef] = Field(default_factory=list)

    # outline
    outline: Optional[Dict[str, Any]] = None       # serialized ExecutionOutline
    current_phase_id: Optional[str] = None
    current_agent_slug: Optional[str] = None
    completed_phase_ids: List[str] = Field(default_factory=list)
    blocked_phase_ids: List[str] = Field(default_factory=list)

    # bounded logs
    facts: List[Fact] = Field(default_factory=list)
    agent_results: List[AgentResult] = Field(default_factory=list)
    planner_steps: List[PlannerStepRecord] = Field(default_factory=list)
    recent_action_signatures: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    # budgets
    iter_count: int = 0
    used_tool_calls: int = 0
    used_wall_time_ms: int = 0

    # final artifacts
    final_answer: Optional[str] = None
    final_error: Optional[str] = None

    # arbitrary runtime state (platform config cache, etc.)
    memory_state: Dict[str, Any] = Field(default_factory=dict)

    finished_at: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    # Mutations                                                          #
    # ------------------------------------------------------------------ #

    def add_fact(self, text: str, *, source: str = "planner", phase_id: Optional[str] = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        if any(f.text == text for f in self.facts):
            return
        self.facts.append(Fact(text=text, source=source, phase_id=phase_id))
        if len(self.facts) > MAX_FACTS:
            self.facts = self.facts[-MAX_FACTS:]

    def add_agent_result(self, result: AgentResult) -> None:
        self.agent_results.append(result)
        if len(self.agent_results) > MAX_AGENT_RESULTS:
            self.agent_results = self.agent_results[-MAX_AGENT_RESULTS:]
        if result.agent_slug:
            self.current_agent_slug = result.agent_slug
        # Promote agent-produced facts into the main fact list
        for fact in result.facts:
            self.add_fact(fact, source=result.agent_slug, phase_id=result.phase_id)

    def add_planner_step(self, step: PlannerStepRecord) -> None:
        self.planner_steps.append(step)
        if len(self.planner_steps) > MAX_PLANNER_STEPS:
            self.planner_steps = self.planner_steps[-MAX_PLANNER_STEPS:]

        sig = step.signature or self._compute_signature(step)
        self.recent_action_signatures.append(sig)
        if len(self.recent_action_signatures) > MAX_RECENT_SIGNATURES:
            self.recent_action_signatures = self.recent_action_signatures[-MAX_RECENT_SIGNATURES:]
        self.iter_count += 1

    def add_open_question(self, question: str) -> None:
        question = (question or "").strip()
        if not question:
            return
        if question in self.open_questions:
            return
        self.open_questions.append(question)

    def consume_open_question(self) -> Optional[str]:
        """Pop the oldest unresolved question (used when triage detects resume)."""
        if not self.open_questions:
            return None
        return self.open_questions.pop(0)

    def mark_phase_completed(self, phase_id: str) -> None:
        if phase_id and phase_id not in self.completed_phase_ids:
            self.completed_phase_ids.append(phase_id)

    def is_phase_completed(self, phase_id: str) -> bool:
        return phase_id in self.completed_phase_ids

    def can_finalize(self) -> bool:
        """True when no must_do phase remains unfinished."""
        if not self.outline:
            return True
        for phase in self.outline.get("phases", []):
            if not phase.get("must_do", True):
                continue
            if phase.get("allow_final_after"):
                continue
            if phase.get("phase_id") not in self.completed_phase_ids:
                return False
        return True

    def detect_loop(self, threshold: int = LOOP_THRESHOLD) -> bool:
        if len(self.recent_action_signatures) < threshold:
            return False
        tail = self.recent_action_signatures[-threshold:]
        return len(set(tail)) == 1

    def set_recent_messages(self, refs: List[ChatMessageRef]) -> None:
        self.recent_messages = refs[-MAX_RECENT_MESSAGES:]

    # ------------------------------------------------------------------ #
    # Views for planner/triage prompts                                   #
    # ------------------------------------------------------------------ #

    def planner_snapshot(self, max_items: int = 10) -> Dict[str, Any]:
        """Compact view for planner input."""
        return {
            "goal": self.goal,
            "current_phase_id": self.current_phase_id,
            "current_agent_slug": self.current_agent_slug,
            "iter_count": self.iter_count,
            "facts": [f.text for f in self.facts[-max_items:]],
            "agent_results": [
                {
                    "agent_slug": r.agent_slug,
                    "summary": r.summary[:400],
                    "phase_id": r.phase_id,
                    "success": r.success,
                }
                for r in self.agent_results[-max_items:]
            ],
            "open_questions": list(self.open_questions[-max_items:]),
            "completed_phase_ids": list(self.completed_phase_ids),
            "recent_actions": list(self.recent_action_signatures[-max_items:]),
        }

    def triage_snapshot(self, max_items: int = 5) -> Dict[str, Any]:
        """Compact view for triage input — what the triage LLM should see."""
        return {
            "dialogue_summary": self.dialogue_summary,
            "open_questions": list(self.open_questions),
            "recent_facts": [f.text for f in self.facts[-max_items:]],
            "status": self.status,
            "has_paused_run": self.status in {"waiting_input", "waiting_confirmation"},
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_signature(step: PlannerStepRecord) -> str:
        parts = [step.kind, step.agent_slug or "-", step.phase_id or "-"]
        payload = "|".join(parts)
        return hashlib.md5(payload.encode()).hexdigest()[:12]
