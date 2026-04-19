"""Runtime memory subsystem.

Post-M6 this package exposes:

    New (persistent, cross-turn):
        * dto.py       — FactDTO, SummaryDTO
        * fact_store.py / summary_store.py — data access
        * fact_extractor.py / summary_compactor.py — LLM helpers
        * builder.py / writer.py — read/write orchestration
        * transport.py — TurnMemory (in-turn, ephemeral)

    Legacy (in-turn runtime state only, NOT persisted anywhere):
        * working_memory.py — WorkingMemory pydantic model, still used
          as the runtime-state carrier that Planner / Synthesizer /
          stages mutate during a turn. Will eventually fold into
          TurnMemory; for now it is a pure in-memory DTO.

The `WorkingMemoryRepository` that persisted runs to the
`execution_memories` table is removed; that table is left as dormant
DDL and can be dropped in a later migration.
"""
from app.runtime.memory.working_memory import (
    WorkingMemory,
    Fact,
    AgentResult,
    PlannerStepRecord,
    ChatMessageRef,
    MAX_FACTS,
    MAX_AGENT_RESULTS,
    MAX_RECENT_SIGNATURES,
)

__all__ = [
    "WorkingMemory",
    "Fact",
    "AgentResult",
    "PlannerStepRecord",
    "ChatMessageRef",
    "MAX_FACTS",
    "MAX_AGENT_RESULTS",
    "MAX_RECENT_SIGNATURES",
]
