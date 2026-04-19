"""
Agent Runtime - ядро для выполнения агентов с tool-call loop
"""
from __future__ import annotations

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.base import ToolHandler
from app.agents.registry import ToolRegistry

__all__ = [
    "ToolContext",
    "ToolResult",
    "ToolHandler",
    "ToolRegistry",
    "RuntimeEvent",
    "RuntimeEventType",
    "PolicyLimits",
    "ExecutionRequest",
    "ExecutionMode",
    "PreflightError",
    "AgentUnavailableError",
]


def __getattr__(name: str):
    if name in {"RuntimeEvent", "RuntimeEventType"}:
        from app.runtime import RuntimeEvent, RuntimeEventType

        return {
            "RuntimeEvent": RuntimeEvent,
            "RuntimeEventType": RuntimeEventType,
        }[name]

    if name == "PolicyLimits":
        from app.agents.runtime.policy import PolicyLimits

        return PolicyLimits

    if name in {"ExecutionRequest", "ExecutionMode", "PreflightError", "AgentUnavailableError"}:
        from app.agents.execution_preflight import (
            ExecutionRequest,
            ExecutionMode,
            PreflightError,
            AgentUnavailableError,
        )

        return {
            "ExecutionRequest": ExecutionRequest,
            "ExecutionMode": ExecutionMode,
            "PreflightError": PreflightError,
            "AgentUnavailableError": AgentUnavailableError,
        }[name]

    raise AttributeError(f"module 'app.agents' has no attribute '{name}'")
