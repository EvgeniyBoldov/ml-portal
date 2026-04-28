from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

from app.runtime.redactor import RuntimeRedactor


class RuntimeTracePackService:
    """Builds deterministic trace-pack payload from AgentRun + steps."""
    TRACE_PACK_VERSION = "runtime.trace_pack.v2"

    TRACE_STEP_TYPES = {
        "user_request",
        "budget_policy",
        "budget_consumed",
        "budget_limit_exceeded",
        "triage_complete",
        "preflight_complete",
        "routing_decision",
        "policy_decision",
        "planner_step",
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
        "confirmation_required",
        "status",
    }

    def __init__(self) -> None:
        self.redactor = RuntimeRedactor()

    def build_trace_pack(self, run: Any) -> Dict[str, Any]:
        steps = sorted(list(getattr(run, "steps", []) or []), key=lambda item: getattr(item, "step_number", 0))

        operations = sorted(self._collect_operations(steps))
        prompt_surfaces = self._collect_prompt_surfaces(steps)
        tool_io = self._collect_tool_io(steps)
        errors = self._collect_errors(steps, run)
        timeline = self._collect_timeline(steps)

        return {
            "trace_pack_version": self.TRACE_PACK_VERSION,
            "run_id": str(getattr(run, "id", "")),
            "agent_slug": str(getattr(run, "agent_slug", "")),
            "status": str(getattr(run, "status", "")),
            "logging_level": str(getattr(run, "logging_level", "")),
            "context_snapshot": self.redactor.redact(getattr(run, "context_snapshot", None)),
            "runtime_config": self.redactor.redact(self._collect_runtime_config(run)),
            "budget": self.redactor.redact(self._collect_budget(steps)),
            "operations": self.redactor.redact(operations),
            "planner_io": self.redactor.redact(self._collect_planner_io(steps)),
            "policy_decisions": self.redactor.redact(self._collect_policy_decisions(steps)),
            "llm_model_config": self.redactor.redact(self._collect_model_config(steps)),
            "prompt_surfaces": self.redactor.redact(prompt_surfaces),
            "tool_io": self.redactor.redact(tool_io),
            "memory_bundle": self.redactor.redact(self._collect_memory_bundle(run, steps)),
            "errors": self.redactor.redact(errors),
            "timeline": self.redactor.redact(timeline),
            "total_steps": len(steps),
        }

    @staticmethod
    def _collect_runtime_config(run: Any) -> Dict[str, Any]:
        snapshot = getattr(run, "context_snapshot", None) or {}
        if not isinstance(snapshot, dict):
            return {}
        config = snapshot.get("runtime_config")
        if isinstance(config, dict):
            return dict(config)
        platform = snapshot.get("platform_config")
        if isinstance(platform, dict):
            return {"platform_config": platform}
        return {}

    def _collect_budget(self, steps: Iterable[Any]) -> Dict[str, Any]:
        policy: Dict[str, Any] = {}
        consumed: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            if step_type == "budget_policy":
                policy.update(data)
                continue
            if step_type in {"budget_consumed", "budget_limit_exceeded"}:
                consumed.append(
                    {
                        "step_number": getattr(step, "step_number", None),
                        "step_type": step_type,
                        "data": data,
                    }
                )
                continue
            if step_type == "status" and data.get("budget"):
                consumed.append(
                    {
                        "step_number": getattr(step, "step_number", None),
                        "step_type": step_type,
                        "data": data.get("budget"),
                    }
                )
        return {
            "policy": policy,
            "consumed": consumed,
        }

    @staticmethod
    def _collect_planner_io(steps: Iterable[Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type not in {"planner_step", "llm_request", "llm_response"}:
                continue
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            entries.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "step_type": step_type,
                    "data": data,
                }
            )
        return entries

    @staticmethod
    def _collect_policy_decisions(steps: Iterable[Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type not in {"routing_decision", "policy_decision", "confirmation_required"}:
                continue
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            entries.append(
                {
                    "step_number": getattr(step, "step_number", None),
                    "step_type": step_type,
                    "data": data,
                }
            )
        return entries

    @staticmethod
    def _collect_model_config(steps: Iterable[Any]) -> Dict[str, Any]:
        for step in steps:
            step_type = str(getattr(step, "step_type", "") or "")
            if step_type not in {"llm_request", "llm_call"}:
                continue
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            return {
                "model": data.get("model"),
                "provider_model": data.get("provider_model") or data.get("model"),
                "temperature": data.get("temperature"),
                "max_tokens": data.get("max_tokens"),
            }
        return {}

    @staticmethod
    def _collect_memory_bundle(run: Any, steps: Iterable[Any]) -> Dict[str, Any]:
        snapshot = getattr(run, "context_snapshot", None) or {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        if isinstance(snapshot.get("memory_bundle"), dict):
            return {"from": "context_snapshot", "bundle": snapshot.get("memory_bundle")}

        for step in steps:
            data = getattr(step, "data", None) or {}
            if not isinstance(data, dict):
                continue
            memory_bundle = data.get("memory_bundle")
            if isinstance(memory_bundle, dict):
                return {
                    "from": f"step:{getattr(step, 'step_type', '')}",
                    "bundle": memory_bundle,
                }
        return {}

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
                    "risk_level": data.get("risk_level"),
                    "side_effects": data.get("side_effects"),
                    "error_code": data.get("error_code"),
                    "retryable": data.get("retryable"),
                    "safe_message": data.get("safe_message"),
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
                    "error_code": (getattr(step, "data", None) or {}).get("error_code")
                    if isinstance(getattr(step, "data", None), dict)
                    else None,
                    "retryable": (getattr(step, "data", None) or {}).get("retryable")
                    if isinstance(getattr(step, "data", None), dict)
                    else None,
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
