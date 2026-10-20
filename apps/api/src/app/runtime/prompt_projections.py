"""Lossless model projections; compatibility aliases remain in persistence."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def task_result_for_prompt(result: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(result)
    if not value.get("answer") and value.get("description"):
        value["answer"] = value["description"]
    if value.get("description") == value.get("answer"):
        value.pop("description", None)
    if "structured_response" not in value and "outputs" in value:
        value["structured_response"] = value["outputs"]
    if "outputs" in value and (value["outputs"] == value.get("structured_response")
                              or value["outputs"] == {"structured_response": value.get("structured_response")}):
        value.pop("outputs")
    return value


def selected_materials(context: dict[str, Any]) -> dict[str, Any]:
    """Planner's task metadata lives in task_brief; this carries only sources."""
    return {key: deepcopy(context[key]) for key in (
        "original_request", "evidence", "conversation_materials", "unavailable_material_refs",
    ) if key in context}


def synthesis_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(context)
    brief = value.get("synthesis_brief") or {}
    if brief.get("user_question") == value.get("user_question"):
        brief.pop("user_question", None)
    run = value.get("run_context") or {}
    run.pop("goal", None)
    if run.get("original_request") == value.get("user_question"):
        run.pop("original_request", None)
    if run.get("answer_requirements") == brief.get("answer_requirements"):
        run.pop("answer_requirements", None)
    value.pop("execution_context", None)  # Derived from the canonical scope_context.
    if value.get("completed_task_reports"):
        value["completed_task_reports"] = [task_result_for_prompt(report) for report in value["completed_task_reports"]]
    summary = value.get("execution_summary") or {}
    # Keep the partial flag; limitations own the user-facing explanation.
    if any(item.get("message") == summary.get("message") for item in value.get("limitations") or []):
        summary.pop("message", None)
    if any(item.get("message") == brief.get("answer_requirements") for item in value.get("limitations") or []):
        brief.pop("answer_requirements", None)
    return value


def preflight_context(project: dict[str, Any], chat: dict[str, Any], *,
                      dialogue: list[dict[str, Any]] | None = None,
                      user_request: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """Scope is supplied once; topic, references and dialogue anchors stay intact."""
    project_value = {key: deepcopy(item) for key, item in project.items()
                     if key == "scope_context" or ("project" in key and item and key != "execution_context")}
    chat_value = deepcopy(chat)
    anchor = chat_value.get("recent_anchor")
    if isinstance(anchor, dict):
        represented = {str(item.get("content") or "") for item in dialogue or []}
        if user_request:
            represented.add(user_request)
        for key in ("user_intent", "assistant_outcome"):
            if anchor.get(key) in represented:
                anchor.pop(key)
    if project.get("scope_context") and isinstance(chat_value.get("focus"), dict):
        focus = chat_value["focus"]
        for key in list(focus):
            if "scope" in key or key in {"team_keys", "project_keys", "suppress_team_default", "suppress_project_default", "project_keys_trust_class"}:
                focus.pop(key)
    return project_value, chat_value
