"""Deterministic advisory signals evaluated before TurnPreflight."""
from __future__ import annotations

import re
from ipaddress import ip_interface
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
    """Recognize live-data requests using bounded current-message signals."""

    JIRA_JQL_RULE = "live_jira_jql_lookup"
    DCBOX_JIRA_RULE = "live_dcbox_jira_lookup"

    _READ_COMMAND = re.compile(
        r"^(?:(?:пожалуйста|please)[, ]+)?(?:найди|найдите|покажи|покажите|проверь|проверьте|"
        r"выполни|выполните|запусти|запустите|получи|расскажи|посмотри|выведи|посчитай|"
        r"find|show|list|run|execute|search|fetch|count|look\s+up)\b", re.IGNORECASE,
    )
    _CONTEXT_DEPENDENT = re.compile(
        r"\b(?:как\s+(?:найти|искать|проверить|выполнить|работает)|объясн\w*|пример\w*|"
        r"синтаксис\w*|предыдущ\w*|прошл\w*\s+ответ\w*|выше|цитат\w*|фраз[ауой]*|"
        r"из\s+(?:(?:стар\w*|прошл\w*)\s+)?(?:переписк\w*|выгруз\w*|файл\w*|лог\w*|"
        r"истори\w*|стар\w*\s+отч[её]т\w*|описани\w*|вложени\w*)|"
        r"how\s+to|explain|example|sample|syntax|previous|earlier|above|quoted|"
        r"from\s+(?:the\s+)?(?:chat|file|old\s+report|export|logs?))\b", re.IGNORECASE,
    )
    _RESTRICTED_SOURCE = re.compile(
        r"\b(?:(?:в|по|из)\s+памят\w*|только\s+(?:из|по)\s+(?:приложенн\w*|предоставленн\w*|"
        r"сохран[её]нн\w*|кэш\w*)|не\s+(?:выполн\w*|запуска\w*|искать|обраща\w*|трогай\w*|ходи\w*)|"
        r"без\s+(?:выполн\w*|запуск\w*|поиск\w*|обращен\w*)|"
        r"(?:in|from)\s+memory|only\s+(?:from|in|using)\s+(?:the\s+)?(?:supplied|cached|saved|provided)|"
        r"(?:without|do\s+not|don't)\s+(?:run\w*|execut\w*|search\w*|query\w*))\b", re.IGNORECASE,
    )
    _QUOTED = re.compile(
        r"(?m)^[ \t]*>[^\n]*|```[\s\S]*?```|«[^»]*»|“[^”]*”|\"[^\"\n]*\"|`[^`\n]*`|(?<!\w)'[^'\n]*'(?!\w)"
    )
    _ADDRESS = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,3})?(?![\w./])")
    _DCBOX = re.compile(r"\bdcbox\b", re.IGNORECASE)
    _JIRA = re.compile(r"\bjira\b", re.IGNORECASE)
    _ISSUES = re.compile(r"\b(?:задач\w*|тикет\w*|issues?|tickets?)\b", re.IGNORECASE)
    _ISSUE_LOOKUP = re.compile(
        r"\b(?:в\s+каких|встреча\w*|упомина\w*|найди\w*|покажи\w*|"
        r"find|which|matching|mentions?)\b", re.IGNORECASE,
    )
    _JQL_QUERY = re.compile(
        r"\bjql(?:[- ]+запрос\w*|\s+query)?(?:\s*:\s*|\s+)(?:```(?:jql)?\s*|[`«“\"]\s*)?"
        r"(?:\(\s*|not\s+)*(?:[\w.]+|\"[^\"\n]+\"|'[^'\n]+'|cf\[\d+\])\s*"
        r"(?:[!<>~]=?|=|in\b|not\s+in\b|is\b|was\b|changed\b)\s*[\w(\"'-]",
        re.IGNORECASE,
    )
    _JQL_EXECUTION_PREFIX = re.compile(
        r"\b(?:выполни\w*|запусти\w*|run|execute)\s+(?:(?:этот|следующий|this|the)\s+)?$",
        re.IGNORECASE,
    )
    _JQL_FILTER_PREFIX = re.compile(
        r"\b(?:по|соответств\w*|using|match(?:ing)?|задач\w*|тикет\w*|issues?|tickets?)\s+"
        r"(?:(?:этому|следующему|this|the)\s+)?$", re.IGNORECASE,
    )

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
    def _unquoted_request(cls, text: str) -> str:
        def keep_source_or_address(match: re.Match[str]) -> str:
            value = match.group()[1:-1].strip()
            if value.casefold() in {"dcbox", "jira"} or cls._ADDRESS.fullmatch(value):
                return value
            return " "

        return cls._QUOTED.sub(keep_source_or_address, text)

    @staticmethod
    def _valid_address(value: str) -> bool:
        try:
            ip_interface(value)
        except ValueError:
            return False
        return True

    @classmethod
    def _explicit_live_rule(cls, text: str) -> str | None:
        if not cls._READ_COMMAND.match(text):
            return None
        unquoted = cls._unquoted_request(text)
        if any(pattern.search(unquoted) for pattern in (
            cls._CONTEXT_DEPENDENT, cls._RESTRICTED_SOURCE, cls._DOCUMENTATION_INTENT,
        )):
            return None
        jira_jql = cls._explicit_jql_request(text)
        clauses = re.split(r"\b(?:и|and)\b", unquoted, maxsplit=1, flags=re.IGNORECASE)
        if len(clauses) == 2:
            inventory, issue_lookup = clauses
            jira_source = cls._JIRA.search(issue_lookup) or (
                jira_jql and re.search(r"\bjql\b", issue_lookup, re.IGNORECASE)
            )
            if (
                cls._DCBOX.search(inventory)
                and any(cls._valid_address(match.group()) for match in cls._ADDRESS.finditer(inventory))
                and jira_source and cls._ISSUES.search(issue_lookup)
                and cls._ISSUE_LOOKUP.search(issue_lookup)
            ):
                return cls.DCBOX_JIRA_RULE
        return cls.JIRA_JQL_RULE if jira_jql else None

    @classmethod
    def _explicit_jql_request(cls, text: str) -> bool:
        jql = cls._JQL_QUERY.search(text)
        if jql is None or any(quote.start() <= jql.start() < quote.end() for quote in cls._QUOTED.finditer(text)):
            return False
        prefix = text[:jql.start()].rstrip() + " "
        return bool(cls._JQL_EXECUTION_PREFIX.search(prefix) or (
            cls._ISSUES.search(prefix) and cls._JQL_FILTER_PREFIX.search(prefix)
        ))

    @classmethod
    def evaluate(
        cls,
        user_request: str,
        available_agents: list[dict[str, object]],
        *,
        recommendation_id: str,
        effective_goal: str | None = None,
        recent_dialogue: list[dict[str, object]] | None = None,
        continuation: dict[str, object] | None = None,
    ) -> RootRouteRecommendation:
        request = (user_request or "").strip()
        text = " ".join(request.split())
        saved_goal = bool(effective_goal and effective_goal.strip() != request)
        explicit_rule = cls._explicit_live_rule(request) if not continuation and not saved_goal else None
        if explicit_rule:
            return RootRouteRecommendation(
                recommendation_id=recommendation_id,
                status="matched",
                rule_id=explicit_rule,
                route_hint="planner",
                signals=["explicit_live_data_request"],
                reason_code="explicit_live_data_request",
                summary="Запрос явно требует актуальной проверки указанных источников.",
            )
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
        if saved_goal:
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
