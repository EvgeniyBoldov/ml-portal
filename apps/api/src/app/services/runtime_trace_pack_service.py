from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


class RuntimeTracePackService:
    """Builds deterministic trace-pack payload from AgentRun + steps."""

    TRACE_STEP_TYPES = {
        "user_request",
        "budget_policy",
        "budget_limit_exceeded",
        "triage_complete",
        "preflight_complete",
        "llm_call",
        "llm_request",
        "llm_response",
        "operation_call",
        "operation_result",
        "tool_call",
        "tool_result",
        "final",
        "final_response",
        "error",
        "waiting_input",
    }

    def build_trace_pack(self, run: Any) -> Dict[str, Any]:
        steps = sorted(list(getattr(run, "steps", []) or []), key=lambda item: getattr(item, "step_number", 0))

        operations = sorted(self._collect_operations(steps))
        prompt_surfaces = self._collect_prompt_surfaces(steps)
        tool_io = self._collect_tool_io(steps)
        errors = self._collect_errors(steps, run)
        timeline = self._collect_timeline(steps)

        return {
            "run_id": str(getattr(run, "id", "")),
            "agent_slug": str(getattr(run, "agent_slug", "")),
            "status": str(getattr(run, "status", "")),
            "logging_level": str(getattr(run, "logging_level", "")),
            "context_snapshot": getattr(run, "context_snapshot", None),
            "operations": operations,
            "prompt_surfaces": prompt_surfaces,
            "tool_io": tool_io,
            "errors": errors,
            "timeline": timeline,
            "total_steps": len(steps),
        }

    def _collect_operations(self, steps: Iterable[Any]) -> Set[str]:
        operations: Set[str] = set()
        for step in steps:
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            for key in ("operation", "operation_slug", "canonical_op_slug", "tool_slug"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    operations.add(value.strip())
            for key in ("operations", "resolved_operations"):
                values = data.get(key)
                if not isinstance(values, list):
                    continue
                for item in values:
                    if isinstance(item, str) and item.strip():
                        operations.add(item.strip())
                    elif isinstance(item, dict):
                        nested = item.get("operation_slug") or item.get("canonical_op_slug")
                        if isinstance(nested, str) and nested.strip():
                            operations.add(nested.strip())
        return operations

    def _collect_prompt_surfaces(self, steps: Iterable[Any]) -> List[Dict[str, Any]]:
        surfaces: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type not in {"llm_request", "llm_call"}:
                continue
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            surfaces.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "step_type": step_type,
                    "model": data.get("model"),
                    "system_prompt": data.get("system_prompt"),
                    "messages": data.get("messages"),
                    "prompt_preview": data.get("prompt_preview"),
                }
            )
        return surfaces

    def _collect_tool_io(self, steps: Iterable[Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type not in {"operation_call", "operation_result", "tool_call", "tool_result"}:
                continue
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            entries.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "step_type": step_type,
                    "operation_slug": data.get("operation_slug") or data.get("canonical_op_slug") or data.get("operation"),
                    "tool_slug": data.get("tool_slug"),
                    "input": data.get("input", data.get("arguments", data.get("parameters"))),
                    "output": data.get("output", data.get("result", data.get("data"))),
                    "error": getattr(step, "error", None) or data.get("error"),
                }
            )
        return entries

    def _collect_errors(self, steps: Iterable[Any], run: Any) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []
        run_error = getattr(run, "error", None)
        if run_error:
            errors.append({"scope": "run", "message": str(run_error)})

        for step in steps:
            step_error = getattr(step, "error", None)
            if not step_error:
                continue
            errors.append(
                {
                    "scope": "step",
                    "step_number": getattr(step, "step_number", None),
                    "step_type": getattr(step, "step_type", None),
                    "message": str(step_error),
                }
            )
        return errors

    def _collect_timeline(self, steps: Iterable[Any]) -> List[Dict[str, Any]]:
        timeline: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type and step_type not in self.TRACE_STEP_TYPES:
                continue
            timeline.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "step_type": step_type,
                    "duration_ms": getattr(step, "duration_ms", None),
                    "created_at": getattr(step, "created_at", None),
                }
            )
        return timeline
