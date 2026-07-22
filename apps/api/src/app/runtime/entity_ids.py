from __future__ import annotations


def planner_orchestrator_id(run_id: str) -> str:
    return f"{run_id}:orchestrator"


def runtime_plan_id(run_id: str) -> str:
    return f"{run_id}:plan"


def runtime_task_id(plan_id: str, task_id: str) -> str:
    return f"{plan_id}:task:{task_id}"


def runtime_attempt_id(task_id: str, attempt_number: int) -> str:
    return f"{task_id}:attempt:{attempt_number}"


def memory_orchestrator_id(run_id: str) -> str:
    return f"{run_id}:memory"


def memory_component_entity_id(run_id: str, component_name: str, index: int) -> str:
    return f"{run_id}:memory:{component_name}:{index}"
