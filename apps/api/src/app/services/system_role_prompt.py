"""Render editable system-role sections without changing their content."""
from __future__ import annotations

import json
from typing import Any, Mapping


ROLE_PROMPT_SECTIONS = (
    ("identity", "IDENTITY"),
    ("mission", "MISSION"),
    ("rules", "RULES"),
    ("safety", "SAFETY"),
    ("output_requirements", "OUTPUT REQUIREMENTS"),
)


def compile_system_role_prompt(
    config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
    *,
    fallback: str = "You are a helpful assistant.",
) -> str:
    """None inherits a section; an explicit empty value clears it."""
    parts: list[str] = []
    effective_override = override or {}
    for field, heading in ROLE_PROMPT_SECTIONS:
        value = effective_override.get(field)
        if value is None:
            value = config.get(field)
        if value:
            parts.append(f"# {heading}\n{value}")
    examples = effective_override.get("examples")
    if examples is None:
        examples = config.get("examples")
    if examples:
        parts.append("# EXAMPLES")
        for index, example in enumerate(examples, 1):
            if not isinstance(example, dict):
                continue
            lines = [f"## Example {index}"]
            for key in ("description", "input", "output"):
                value = example.get(key)
                if value is None:
                    continue
                rendered = value if isinstance(value, str) else json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"),
                )
                lines.append(f"{key.capitalize()}: {rendered}")
            parts.append("\n".join(lines))
    # Legacy prompt-only configurations remain usable, including structured roles.
    if parts:
        return "\n\n".join(parts)
    if any(effective_override.get(key) is not None for key, _ in ROLE_PROMPT_SECTIONS):
        return fallback
    return str(config.get("prompt") or fallback)
