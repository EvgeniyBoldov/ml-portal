"""TurnMemory — the runtime's in-turn transport object.

This is NOT a persisted entity.

Named `TurnMemory` (not `WorkingMemory`) because the legacy runtime-state
object in `app.runtime.memory.working_memory.WorkingMemory` still carries
the per-run execution state used by the planner/stages during the turn.
Once the legacy WorkingMemory is retired (M6), this class will carry all
turn state and rename is trivial. It lives for the duration of one
pipeline turn, is produced by `MemoryBuilder` at the top and consumed
by `MemoryWriter` at the bottom. The Planner and Synthesizer mutate
its `agent_results` / `planner_steps` / `final_answer` fields as the
turn progresses; everything else is a read-only snapshot taken at
`MemoryBuilder.build` time.

Keeping this a plain dataclass (not pydantic) keeps field access cheap
on the hot path and makes it obvious that no validation happens here —
validation belongs at the boundary (FactExtractor output, HTTP admin API).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.runtime.memory.dto import FactDTO, SummaryDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet


@dataclass
class TurnMemory:
    """Per-turn state passed through stages."""

    # --- identity ---------------------------------------------------------
    chat_id: Optional[UUID]
    user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    turn_number: int

    # --- read-only snapshot taken by MemoryBuilder ------------------------
    goal: str
    summary: SummaryDTO
    retrieved_facts: List[FactDTO] = field(default_factory=list)

    # --- mutated during the turn by the pipeline --------------------------
    agent_results: List[AgentResultSnippet] = field(default_factory=list)
    planner_steps: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    final_error: Optional[str] = None

    # --- convenience ------------------------------------------------------
    def iter_known_subjects(self):
        """Yield (subject, value) for retrieved facts — passed to the
        extractor as `known_facts` so it can dedupe."""
        for f in self.retrieved_facts:
            yield f.subject, f.value
