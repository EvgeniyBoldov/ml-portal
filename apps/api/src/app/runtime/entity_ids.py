from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


_NAMESPACE = uuid5(NAMESPACE_URL, "ml-portal:runtime-entities")


def _id(kind: str, *parts: object) -> str:
    """Return a stable opaque UUID for one runtime entity."""
    return str(uuid5(_NAMESPACE, ":".join([kind, *(str(part) for part in parts)])))


def planner_orchestrator_id(run_id: str) -> str:
    return _id("orchestrator", run_id)


def runtime_plan_id(run_id: str) -> str:
    return _id("plan", run_id)


def runtime_task_id(plan_id: str, task_id: str) -> str:
    return _id("task", plan_id, task_id)


def runtime_attempt_id(task_id: str, attempt_number: int) -> str:
    return _id("attempt", task_id, attempt_number)


def attempt_id(task_id: str, attempt_number: int) -> str:
    """Canonical attempt identity helper used by orchestration code."""
    return runtime_attempt_id(task_id, attempt_number)


def memory_orchestrator_id(run_id: str) -> str:
    return _id("memory-orchestrator", run_id)


def memory_component_entity_id(run_id: str, component_name: str, index: int) -> str:
    return _id("memory-component", run_id, component_name, index)


def planner_iteration_id(run_id: str, iteration_number: int) -> str:
    return _id("planner-iteration", run_id, iteration_number)


def step_id(iteration_id: str, step_number: int, task_id: str) -> str:
    return _id("step", iteration_id, step_number, task_id)


def agent_execution_id(iteration_id: str, task_id: str, attempt_number: int) -> str:
    return _id("agent-execution", iteration_id, task_id, attempt_number)


def checkpoint_id(run_id: str, kind: str, key: str) -> str:
    return _id("checkpoint", run_id, kind, key)


def synthesis_run_id(run_id: str, ordinal: int = 1) -> str:
    return _id("synthesis", run_id, ordinal)


def call_id(agent_id: str, kind: str, ordinal: int) -> str:
    return _id(kind, agent_id, ordinal)


def interaction_id(run_id: str, ordinal: int = 1) -> str:
    return _id("interaction", run_id, ordinal)
