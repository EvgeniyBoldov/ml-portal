from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from app.services.runtime_evaluation_harness import default_runtime_eval_cases, evaluate_runtime_cases
from app.services.runtime_trace_pack_service import RuntimeTracePackService


class RuntimeDiagnosticsService:
    """Build high-level admin diagnostics summary for a single run."""

    def __init__(self) -> None:
        self.trace_pack = RuntimeTracePackService()

    def build_summary(self, run: Any) -> Dict[str, Any]:
        trace_pack = self.trace_pack.build_trace_pack(run)
        runtime_events = self._runtime_events_from_steps(getattr(run, "steps", []) or [])
        eval_results = evaluate_runtime_cases(default_runtime_eval_cases(), runtime_events)

        return {
            "run_id": UUID(str(getattr(run, "id"))),
            "status": str(getattr(run, "status", "")),
            "agent_slug": str(getattr(run, "agent_slug", "")),
            "operations": list(trace_pack.get("operations") or []),
            "memory_sections": self._memory_sections(trace_pack.get("memory_bundle")),
            "blocked_or_confirmed_steps": self._blocked_or_confirmed_steps(trace_pack),
            "eval_summary": [
                {
                    "case_key": item.case_key,
                    "passed": item.passed,
                    "score": item.score,
                    "dimensions": {
                        "tool_choice_score": item.dimensions.tool_choice_score,
                        "memory_selection_score": item.dimensions.memory_selection_score,
                        "grounding_score": item.dimensions.grounding_score,
                        "terminal_behavior_score": item.dimensions.terminal_behavior_score,
                        "safety_score": item.dimensions.safety_score,
                    },
                    "notes": list(item.notes),
                }
                for item in eval_results
            ],
        }

    @staticmethod
    def _runtime_events_from_steps(steps: List[Any]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for step in steps:
            events.append(
                {
                    "type": str(getattr(step, "step_type", "") or ""),
                    "data": dict(getattr(step, "data", None) or {}),
                    "error": getattr(step, "error", None),
                }
            )
        return events

    @staticmethod
    def _memory_sections(memory_bundle_payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(memory_bundle_payload, dict):
            return []
        bundle = memory_bundle_payload.get("bundle")
        if not isinstance(bundle, dict):
            return []
        sections = bundle.get("sections")
        if not isinstance(sections, list):
            return []
        result: List[Dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            items = section.get("items")
            result.append(
                {
                    "name": section.get("name"),
                    "item_count": len(items) if isinstance(items, list) else 0,
                    "selection_reason": section.get("selection_reason"),
                }
            )
        return result

    @staticmethod
    def _blocked_or_confirmed_steps(trace_pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for decision in trace_pack.get("policy_decisions", []) or []:
            if not isinstance(decision, dict):
                continue
            step_type = str(decision.get("step_type") or "")
            if step_type not in {"policy_decision", "confirmation_required", "routing_decision"}:
                continue
            data = decision.get("data")
            items.append(
                {
                    "step_number": decision.get("step_number"),
                    "step_type": step_type,
                    "data": data if isinstance(data, dict) else {},
                }
            )
        return items
