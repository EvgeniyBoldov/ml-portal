"""Stable section identities for document evidence."""
from __future__ import annotations

import re
from typing import Any


def split_canonical_sections(text: str, *, max_chars: int = 5_000) -> list[dict[str, Any]]:
    """Create bounded addressable sections while preserving paragraph boundaries."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    sections: list[dict[str, Any]] = []
    parts: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text or ""):
        raw = match.group(0)
        stripped = raw.strip()
        if stripped:
            start = match.start() + len(raw) - len(raw.lstrip())
            parts.append((start, start + len(stripped), stripped))

    buffer: list[tuple[int, int, str]] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        rendered = "\n\n".join(part[2] for part in buffer)
        label = rendered.splitlines()[0][:120] if rendered else f"section {len(sections) + 1}"
        sections.append({
            "id": f"section-{len(sections) + 1}", "label": label, "text": rendered,
            "start_offset": buffer[0][0], "end_offset": buffer[-1][1],
        })
        buffer, buffer_len = [], 0

    for start, end, paragraph in parts:
        chunks = [(start + index, min(start + index + max_chars, end), paragraph[index:index + max_chars])
                  for index in range(0, len(paragraph), max_chars)]
        for chunk_start, chunk_end, chunk in chunks:
            extra = 2 if buffer else 0
            if buffer and buffer_len + extra + len(chunk) > max_chars:
                flush()
            buffer.append((chunk_start, chunk_end, chunk))
            buffer_len += (2 if buffer_len else 0) + len(chunk)
            if len(chunk) == max_chars:
                flush()
    flush()
    return sections
