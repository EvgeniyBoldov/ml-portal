from __future__ import annotations

from typing import Any, Dict, List

from app.agents.contracts import HelperSummary


class RuntimeHelperSummaryService:
    """Builds compact helper summary payload for orchestration runtime."""

    def build(
        self,
        *,
        request_text: str,
        messages: List[Dict[str, Any]],
    ) -> HelperSummary:
        facts: List[str] = []
        open_questions: List[str] = []
        checked_sources: List[str] = []

        for message in messages[-8:]:
            role = message.get("role", "")
            content = message.get("content", "")
            if isinstance(content, dict):
                content = content.get("text", str(content))
            content_text = str(content).strip()
            if not content_text:
                continue

            if role == "assistant":
                facts.append(content_text[:300])
                lowered = content_text.lower()
                if "regламент" in lowered or "policy" in lowered or "document" in lowered:
                    checked_sources.append(content_text[:120])
            elif role == "user" and "?" in content_text:
                open_questions.append(content_text[:300])

        return HelperSummary(
            goal=request_text,
            facts=facts[:5],
            checked_sources=checked_sources[:5],
            open_questions=open_questions[:5],
        )
