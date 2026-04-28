"""Runtime input builders for planner/synthesizer surfaces."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.runtime.turn_state import RuntimeTurnState


MAX_CONVERSATION_SUMMARY_CHARS = 3000
MAX_POLICIES_TEXT_CHARS = 1200
MAX_AGENT_DESCRIPTION_CHARS = 280


class PlannerInputBuilder:
    """Build structured planner payload from runtime state."""

    def build(
        self,
        *,
        runtime_state: RuntimeTurnState,
        available_agents: List[Dict[str, Any]],
        outline: Optional[Dict[str, Any]],
        platform_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        state = runtime_state

        # Conversation context from memory_bundle if available
        conversation_summary = ""
        if state.memory_bundle and state.memory_bundle.sections:
            for section in state.memory_bundle.sections:
                if section.name == "conversation" and section.items:
                    conversation_summary = section.items[0].text[:MAX_CONVERSATION_SUMMARY_CHARS]
                    break

        return {
            "goal": state.goal,
            "conversation_summary": conversation_summary,
            "available_agents": [
                {
                    "slug": item.get("slug"),
                    "description": self._trim_text(
                        item.get("description", ""),
                        MAX_AGENT_DESCRIPTION_CHARS,
                    ),
                }
                for item in available_agents
                if item.get("slug")
            ],
            "execution_outline": outline,
            "memory": state.planner_snapshot(),
            "policies": self._trim_text(
                (platform_config or {}).get("policies_text") or "default",
                MAX_POLICIES_TEXT_CHARS,
            ),
        }

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit]


class SynthesizerInputBuilder:
    """Build user-facing synthesis prompt from runtime state."""

    def build(
        self,
        *,
        runtime_state: RuntimeTurnState,
        planner_hint: Optional[str],
        system_prompt: str,
    ) -> List[Dict[str, str]]:
        state = runtime_state

        parts: List[str] = []
        goal = state.goal
        parts.append(f"Цель: {goal or '(не указана)'}")

        # Conversation context from memory_bundle if available
        conversation_summary = ""
        if state.memory_bundle and state.memory_bundle.sections:
            for section in state.memory_bundle.sections:
                if section.name == "conversation" and section.items:
                    conversation_summary = section.items[0].text[:1500]
                    break
        if conversation_summary:
            parts.append(f"Контекст диалога:\n{conversation_summary}")

        state_results = list(state.agent_results)
        if state_results:
            parts.append("Результаты агентов:")
            for item in state_results[-8:]:
                slug = str(item.get("agent_slug") or item.get("agent") or "agent")
                success = bool(item.get("success", True))
                summary = str(item.get("summary") or "")
                status = "OK" if success else "FAIL"
                parts.append(f"- [{slug}] ({status}) {summary[:400]}")

        if state.memory_bundle.sections:
            parts.append("Отобранная память (sections):")
            for section in state.memory_bundle.sections[:6]:
                if not section.items:
                    continue
                parts.append(f"- {section.name}: {len(section.items)} items")

        state_facts = list(state.runtime_facts)
        if state_facts:
            parts.append("Факты:")
            for fact in state_facts[-20:]:
                parts.append(f"- {fact.text[:200]}")

        if planner_hint:
            parts.append(f"Подсказка планировщика: {planner_hint[:400]}")

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(parts)},
        ]
