"""
Agent Runtime - ядро для выполнения агентов с tool-call loop
"""
from app.agents.context import ToolContext, ToolResult, RunContext
from app.agents.handlers.base import ToolHandler
from app.agents.registry import ToolRegistry
from app.agents.runtime import AgentRuntime, RuntimeEvent, RuntimeEventType, PolicyLimits
from app.agents.router import (
    AgentRouter,
    ExecutionRequest,
    ExecutionMode,
    AgentRouterError,
    AgentUnavailableError,
)

__all__ = [
    "ToolContext",
    "ToolResult", 
    "RunContext",
    "ToolHandler",
    "ToolRegistry",
    "AgentRuntime",
    "RuntimeEvent",
    "RuntimeEventType",
    "PolicyLimits",
    "AgentRouter",
    "ExecutionRequest",
    "ExecutionMode",
    "AgentRouterError",
    "AgentUnavailableError",
]
