"""
PolicyLimits — execution constraints from policy_data and limit_data.
GenerationParams — LLM generation parameters (model, temperature, max_tokens).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class GenerationParams:
    """LLM generation parameters resolved from AgentVersion + OrchestrationSettings."""

    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None


@dataclass
class PolicyLimits:
    """Extracted execution constraints for runtime enforcement."""

    max_steps: int = 20
    max_tool_calls_total: int = 50
    max_wall_time_ms: int = 600_000
    tool_timeout_ms: int = 60_000
    max_retries: int = 3
    streaming_enabled: bool = True
    citations_required: bool = False
    allow_parallel_tool_calls: bool = False

    @classmethod
    def from_policy(
        cls,
        policy: Dict[str, Any],
        limit: Optional[Dict[str, Any]] = None,
    ) -> PolicyLimits:
        """Extract limits from policy_data dict and optional limit_data dict.

        policy_data comes from PolicyVersion.policy_json (structured behavioral rules).
        limit_data comes from LimitVersion fields (execution constraints).
        limit_data values override policy_data values when both are present.
        """
        execution = policy.get("execution", {})
        retry = policy.get("retry", {})
        output = policy.get("output", {})
        tool_exec = policy.get("tool_execution", {})

        lim = limit or {}

        return cls(
            max_steps=lim.get("max_steps", execution.get("max_steps", 10)),
            max_tool_calls_total=lim.get(
                "max_tool_calls", execution.get("max_tool_calls_total", 50),
            ),
            max_wall_time_ms=lim.get(
                "max_wall_time_ms", execution.get("max_wall_time_ms", 300_000),
            ),
            tool_timeout_ms=lim.get(
                "tool_timeout_ms", execution.get("tool_timeout_ms", 30_000),
            ),
            max_retries=lim.get("max_retries", retry.get("max_retries", 3)),
            streaming_enabled=execution.get("streaming_enabled", True),
            citations_required=output.get("citations_required", False),
            allow_parallel_tool_calls=tool_exec.get("allow_parallel_tool_calls", False),
        )
