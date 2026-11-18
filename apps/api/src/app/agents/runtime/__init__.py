"""
Sub-agent runtime primitives — used by the v3 pipeline's AgentExecutor.

The top-level orchestration (triage + planner + synthesizer) lives in
`app.runtime` (v3). This package owns only the building blocks that execute
a single agent with a tool-call loop:

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

from typing import Any

from app.agents.runtime.policy import GenerationParams, PolicyLimits


def __getattr__(name: str) -> Any:
    # Importing result_context must not initialize app.runtime while
    # chat_context_contracts is still defining ChatContextSnapshot.  Keep the
    # legacy event exports available, but resolve them only when requested.
    if name in {"RuntimeEvent", "RuntimeEventType"}:
        from app.runtime import events

        return getattr(events, name)
    raise AttributeError(name)


__all__ = [
    "RuntimeEvent",
    "RuntimeEventType",
    "PolicyLimits",
    "GenerationParams",
]
