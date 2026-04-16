"""
RunContextCompact — bounded context for planner.

Keeps planner input stable-sized regardless of how many steps the run takes.
Facts are deterministic one-liners extracted from Observation (no LLM needed).
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from app.agents.contracts import (
    ActionType,
    AvailableActions,
    NextAction,
    Observation,
    ObservationStatus,
)


MAX_FACTS = 20
MAX_RECENT_SIGNATURES = 10
LOOP_THRESHOLD = 3


def _action_signature(action: NextAction) -> str:
    """Deterministic signature for loop detection: (type, operation_slug, op, hash(input))."""
    parts = [action.type.value]
    if action.type == ActionType.OPERATION_CALL and action.operation:
        parts.append(action.operation.intent.operation_slug)
        parts.append(action.operation.intent.op)
        input_str = json.dumps(action.operation.input, sort_keys=True, default=str)
        parts.append(hashlib.md5(input_str.encode()).hexdigest()[:8])
    elif action.type == ActionType.AGENT_CALL and action.agent:
        parts.append(action.agent.agent_slug)
    elif action.type == ActionType.ASK_USER and action.ask_user:
        parts.append(hashlib.md5(action.ask_user.question.encode()).hexdigest()[:8])
    return "|".join(parts)


def observation_to_fact(obs: Observation, operation_slug: str = "", op: str = "") -> str:
    """Convert Observation into a single-line fact string."""
    prefix = f"[{operation_slug}.{op}]" if operation_slug else "[result]"
    if obs.status == ObservationStatus.OK:
        return f"{prefix} OK: {obs.summary}"
    elif obs.status == ObservationStatus.ERROR:
        err_msg = obs.error.message if obs.error else "unknown error"
        return f"{prefix} ERROR: {err_msg}"
    else:
        return f"{prefix} BLOCKED: {obs.summary}"


def trim_observation_output(output: Dict[str, Any], max_bytes: int = 3000) -> Dict[str, Any]:
    """Trim observation output to keep it compact for planner context."""
    serialized = json.dumps(output, default=str, ensure_ascii=False)
    if len(serialized) <= max_bytes:
        return output

    trimmed: Dict[str, Any] = {}
    current_size = 2  # {}
    for key, value in output.items():
        entry = json.dumps({key: value}, default=str, ensure_ascii=False)
        if current_size + len(entry) > max_bytes:
            trimmed["_truncated"] = True
            break
        trimmed[key] = value
        current_size += len(entry)
    return trimmed


@dataclass
class RunContextCompact:
    """Bounded planner context that doesn't grow linearly with steps."""

    goal: str = ""
    facts: Deque[str] = field(default_factory=lambda: deque(maxlen=MAX_FACTS))
    last_observation: Optional[Observation] = None
    iter_count: int = 0
    recent_signatures: Deque[str] = field(
        default_factory=lambda: deque(maxlen=MAX_RECENT_SIGNATURES)
    )

    def add_fact(self, fact: str) -> None:
        if fact and fact not in self.facts:
            self.facts.append(fact)

    def record_action(self, action: NextAction) -> None:
        sig = _action_signature(action)
        self.recent_signatures.append(sig)
        self.iter_count += 1

    def update_from_observation(
        self, obs: Observation, operation_slug: str = "", op: str = ""
    ) -> None:
        self.last_observation = obs
        fact = observation_to_fact(obs, operation_slug, op)
        self.add_fact(fact)

    def is_looping(self) -> bool:
        """Detect if the last LOOP_THRESHOLD actions have the same signature."""
        if len(self.recent_signatures) < LOOP_THRESHOLD:
            return False
        tail = list(self.recent_signatures)[-LOOP_THRESHOLD:]
        return len(set(tail)) == 1

    def to_planner_input(self, available_actions: AvailableActions) -> Dict[str, Any]:
        """Build compact JSON for planner prompt."""
        result: Dict[str, Any] = {
            "goal": self.goal,
            "facts": list(self.facts),
            "iter": self.iter_count,
        }
        if self.last_observation:
            result["last_observation"] = {
                "status": self.last_observation.status.value,
                "summary": self.last_observation.summary,
                "output": trim_observation_output(self.last_observation.output),
            }
        result["available_operations"] = [
            {
                "operation_slug": t.operation_slug,
                "op": t.op,
                "name": t.name or "",
                "data_instance_slug": t.data_instance_slug or "",
                "description": t.description or "",
                "side_effects": t.side_effects,
                "risk_level": t.risk_level,
            }
            for t in available_actions.operations
        ]
        return result
