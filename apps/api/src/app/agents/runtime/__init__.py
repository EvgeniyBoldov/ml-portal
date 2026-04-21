"""
Sub-agent runtime primitives — used by the v3 pipeline's AgentExecutor.

The top-level orchestration (triage + planner + synthesizer) lives in
`app.runtime` (v3). This package owns only the building blocks that execute
a single agent with a tool-call loop:

- events.py                 — RuntimeEvent, RuntimeEventType
- policy.py                 — PolicyLimits, GenerationParams
- session.py                — RunSession (lifecycle logging)
- llm.py                    — LLMAdapter (call + stream)
- tools.py                  — OperationExecutor
- agent_prompt_renderer.py  — AgentPromptRenderer
- base.py                   — BaseRuntime (abstract)
- agent.py                  — AgentToolRuntime (sub-agent with tool loop)
- prompt_assembler.py       — PromptAssembler
"""
from __future__ import annotations

from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.policy import GenerationParams, PolicyLimits

__all__ = [
    "RuntimeEvent",
    "RuntimeEventType",
    "PolicyLimits",
    "GenerationParams",
]
