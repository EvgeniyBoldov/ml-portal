from __future__ import annotations

import re
from typing import Optional


def extract_balanced_json(text: str, start: int) -> Optional[str]:
    """Extract balanced JSON object starting at '{' index."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def extract_json_from_text(text: str) -> Optional[str]:
    """Extract first JSON object from plain text or markdown fence."""
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    brace_start = text.find("{")
    if brace_start < 0:
        return None
    return extract_balanced_json(text, brace_start)
