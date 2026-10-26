"""Deterministic advisory signals evaluated before TurnPreflight."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RootRouteRecommendation(BaseModel):
    """A bounded hint for TurnPreflight; never an effective route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation_id: str = Field(min_length=1)
    status: Literal["matched", "unmatched"]
    rule_id: str | None = None
    route_hint: Literal["planner", "synthesis", "tool_call"] | None = None
    source_agent_hint: str | None = None
    signals: list[str] = Field(default_factory=list)
    reason_code: str
    summary: str


class RootRoutePolicy:
    """Recommend planner for likely live NetBox inventory lookups."""

    _INVENTORY_TERMS = re.compile(r"\b(?:netbox|инвентори|inventory)\b", re.IGNORECASE)
    _RECORD_INTENT = re.compile(
        r"\b(?:посмотр\w*|покаж\w*|найд\w*|список|какие|какой|какая|какое|сколько|есть|"
        r"show|list|find|which|what|how\s+many)\b",
        re.IGNORECASE,
    )
    _DOCUMENTATION_INTENT = re.compile(
        r"\b(?:как\s+(?:работает|устроен|вести)|инструкц\w*|регламент\w*|процесс\w*|"
        r"документац\w*|описание|что\s+такое|how\s+to|what\s+(?:is|does)|meaning|definition|"
        r"documentation|docs|process)\b",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(
        cls,
        user_request: str,
        available_agents: list[dict[str, object]],
        *,
        recommendation_id: str,
        effective_goal: str | None = None,
        recent_dialogue: list[dict[str, object]] | None = None,
    ) -> RootRouteRecommendation:
        text = " ".join((user_request or "").split())
        inventory_agent_available = any(
            str(agent.get("slug") or "").strip() == "inventory.netbox"
            for agent in available_agents
        )
        has_inventory_source = bool(cls._INVENTORY_TERMS.search(text))
        has_record_intent = bool(cls._RECORD_INTENT.search(text))
        is_documentation_request = bool(cls._DOCUMENTATION_INTENT.search(text))
        signals = tuple(
            name for name, matched in (
                ("inventory_source_mentioned", has_inventory_source),
                ("current_records_requested", has_record_intent),
                ("inventory_agent_available", inventory_agent_available),
                ("documentation_request", is_documentation_request),
            ) if matched
        )
        likely_live_inventory_request = (
            has_inventory_source and has_record_intent and not is_documentation_request
        )
        if recent_dialogue:
            signals += ("dialogue_context_available",)
        if effective_goal and effective_goal.strip() != text:
            signals += ("saved_goal_available",)
        return RootRouteRecommendation(
            recommendation_id=recommendation_id,
            status="matched" if likely_live_inventory_request else "unmatched",
            rule_id="live_netbox_inventory_lookup" if likely_live_inventory_request else None,
            route_hint="planner" if likely_live_inventory_request else None,
            source_agent_hint="inventory.netbox" if likely_live_inventory_request and inventory_agent_available else None,
            signals=list(signals),
            reason_code=(
                "source_not_available" if likely_live_inventory_request and not inventory_agent_available
                else "likely_live_inventory_lookup" if likely_live_inventory_request
                else "no_matching_rule"
            ),
            summary=(
                "Похоже, запрошены актуальные записи NetBox. Это рекомендация; TurnPreflight должен проверить смысл запроса с учётом диалога."
                if likely_live_inventory_request and inventory_agent_available else
                "Запрошены актуальные записи NetBox, но разрешённый агент источника не найден; TurnPreflight должен выбрать честный маршрут."
                if likely_live_inventory_request else
                "Подходящее правило не найдено; TurnPreflight принимает решение по запросу и контексту диалога."
            ),
        )
