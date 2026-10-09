"""Approximate token usage for telemetry when a provider omits usage."""


def estimate_tokens(text: str) -> int:
    raw = (text or "").strip()
    return max(1, len(raw) // 4) if raw else 0
