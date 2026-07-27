"""
Runtime v3 — agentic pipeline with componentized memory and persisted task graphs.

Public surface:
    from app.runtime import RuntimePipeline, PipelineRequest, RuntimeEvent, RuntimeEventType

Design goals:
    * Componentized memory: MemoryBundle assembled per-turn from MemoryComponents
    * Planner produces a persisted task graph; orchestrator owns execution
    * Task attempts distinguish technical failures from valid agent outcomes
    * Clean contracts: PlanPatch, TaskRequest, AgentTaskResult, RuntimeTurnState
"""
from app.runtime.events import RuntimeEvent, RuntimeEventType, OrchestrationPhase
from app.runtime.contracts import (
    PipelineRequest,
    PipelineStopReason,
)
from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    PlanPatch,
    PlanRequest,
    TaskAttemptFailure,
    TaskRequest,
)


def __getattr__(name: str):
    # Lazy: avoids a circular import via
    #   pipeline → services.runtime_event_logger
    #   → app.runtime.events (which re-enters this package's __init__).
    if name == "RuntimePipeline":
        from app.runtime.pipeline import RuntimePipeline

        return RuntimePipeline
    raise AttributeError(name)


__all__ = [
    "RuntimePipeline",
    "PipelineRequest",
    "RuntimeEvent",
    "RuntimeEventType",
    "OrchestrationPhase",
    "PipelineStopReason",
    "PlanPatch",
    "PlanRequest",
    "TaskRequest",
    "AgentTaskResult",
    "TaskAttemptFailure",
]
