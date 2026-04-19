"""Pipeline stages — the two discrete phases of a runtime turn.

Post-M5: triage is dead. The planner absorbed direct_answer / clarify /
resume, so the pipeline is:

    MemoryBuilder → PlanningStage → FinalizationStage? → MemoryWriter
"""
from app.runtime.stages.planning_stage import PlanningOutcome, PlanningStage
from app.runtime.stages.finalization_stage import FinalizationStage

__all__ = [
    "PlanningStage",
    "PlanningOutcome",
    "FinalizationStage",
]
