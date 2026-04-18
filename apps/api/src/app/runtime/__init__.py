"""
Runtime v3 — agentic pipeline with memory, triage, and next-step planner.

Public surface:
    from app.runtime import RuntimePipeline, PipelineRequest, RuntimeEvent, RuntimeEventType

Design goals:
    * Single Working Memory model persisted in `execution_memories` table
    * Two-stage decision making: Triage (fast, answer/clarify/plan/resume),
      then Planner (step-by-step: agent_call / ask_user / final / abort)
    * Flat pipeline: no thin-wrapper orchestrators, one class owns the flow
    * Clean contracts: NextStep, TriageDecision, WorkingMemory
"""
from app.runtime.events import RuntimeEvent, RuntimeEventType, OrchestrationPhase
from app.runtime.contracts import (
    PipelineRequest,
    TriageDecision,
    TriageIntent,
    NextStep,
    NextStepKind,
    PipelineStopReason,
)
from app.runtime.memory.working_memory import WorkingMemory, Fact, AgentResult
from app.runtime.pipeline import RuntimePipeline

__all__ = [
    "RuntimePipeline",
    "PipelineRequest",
    "RuntimeEvent",
    "RuntimeEventType",
    "OrchestrationPhase",
    "TriageDecision",
    "TriageIntent",
    "NextStep",
    "NextStepKind",
    "PipelineStopReason",
    "WorkingMemory",
    "Fact",
    "AgentResult",
]
