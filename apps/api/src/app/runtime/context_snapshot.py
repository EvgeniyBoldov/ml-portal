from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from app.runtime.budgets.schema import EntityLimits, RunLimits


def normalize_logging_level(value: Optional[str]) -> str:
    normalized = str(value or "brief").strip().lower()
    if normalized in {"none", "errors", "brief", "full"}:
        return normalized
    return "brief"


def serialize_limits(limits: EntityLimits | RunLimits | Dict[str, Any] | None) -> Optional[Dict[str, int]]:
    if limits is None:
        return None

    source: Dict[str, Any]
    if isinstance(limits, dict):
        source = limits
    else:
        source = {
            "planner_steps": getattr(limits, "planner_steps", None),
            "agent_steps": getattr(limits, "agent_steps", None),
            "tool_calls": getattr(limits, "tool_calls", None),
            "tokens_total": getattr(limits, "tokens_total", None),
            "retries": getattr(limits, "retries", None),
            "wall_time_ms": getattr(limits, "wall_time_ms", None),
        }

    payload = {
        key: int(value)
        for key, value in source.items()
        if isinstance(value, int) and value > 0
    }
    return payload or None


def prompt_snapshot(prompt: Optional[str], logging_level: Optional[str]) -> Dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        return {}

    level = normalize_logging_level(logging_level)
    if level == "full":
        return {"system_prompt": text}

    return {
        "system_prompt_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def compact_snapshot(
    *,
    inputs: Optional[Dict[str, Any]] = None,
    prompt: Optional[Dict[str, Any]] = None,
    limits: Optional[Dict[str, Any]] = None,
    rbac: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    snapshot: Dict[str, Any] = {}
    if inputs:
        snapshot["inputs"] = {key: value for key, value in inputs.items() if value not in (None, "", [], {})}
    if prompt:
        snapshot.update(prompt)
    if limits:
        snapshot["limits"] = limits
    if rbac:
        snapshot["rbac"] = rbac
    if meta:
        snapshot["meta"] = {key: value for key, value in meta.items() if value not in (None, "", [], {})}
    return snapshot or None
