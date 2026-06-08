from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime.contracts import PipelineStopReason
from app.runtime.stages.planner_call_agent_dispatcher import CallAgentDispatchResult
from app.runtime.stages.planner_step_dispatcher import TerminalDispatchResult


class PlanningOutcomeMapper:
    TERMINAL_KIND_MAP = {
        "direct": "DIRECT",
        "needs_final": "NEEDS_FINAL",
        "paused": "PAUSED",
        "aborted": "ABORTED",
    }
    CALL_AGENT_KIND_MAP = {
        "paused": "PAUSED",
        "needs_final": "NEEDS_FINAL",
    }

    @staticmethod
    def from_terminal_result(result: TerminalDispatchResult) -> Dict[str, Any]:
        return {
            "outcome_kind": result.outcome_kind,
            "stop_reason": result.stop_reason,
            "answer_brief": result.answer_brief,
            "final_answer_strategy": result.final_answer_strategy,
            "error_message": result.error_message,
        }

    @staticmethod
    def from_call_agent_result(result: CallAgentDispatchResult) -> Optional[Dict[str, Any]]:
        if result.outcome == "paused":
            return {"outcome_kind": "paused", "stop_reason": PipelineStopReason.WAITING_CONFIRMATION}
        if result.outcome == "needs_final":
            return {
                "outcome_kind": "needs_final",
                "stop_reason": PipelineStopReason.FAILED,
                "answer_brief": None,
            }
        return None
