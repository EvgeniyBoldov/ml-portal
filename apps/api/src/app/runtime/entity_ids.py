from __future__ import annotations


def planner_orchestrator_id(run_id: str) -> str:
    return f"{run_id}:orchestrator"


def memory_orchestrator_id(run_id: str) -> str:
    return f"{run_id}:memory"


def memory_component_entity_id(run_id: str, component_name: str, index: int) -> str:
    return f"{run_id}:memory:{component_name}:{index}"
