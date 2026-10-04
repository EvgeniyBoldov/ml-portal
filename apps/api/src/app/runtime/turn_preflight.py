"""Root turn routing before planner or synthesizer."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import SynthesisBrief
from app.services.memory_scope_catalog import resolve_memory_scopes
from app.runtime.memory.effective_scope import ScopeSelection
from app.runtime.memory.search_contract import MemorySearchInput


class TaskBrief(BaseModel):
    goal: str = Field(..., min_length=1)
    project_hints: list[str] = Field(default_factory=list)
    scope_keys: list[str] = Field(default_factory=list)
    scope_mode: Literal["inherit", "replace"] = "inherit"
    entity_hints: list[str] = Field(default_factory=list)
    direction: str = Field(..., min_length=1)
    constraints: list[str] = Field(default_factory=list)
    expected_result: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class DirectAnswerBrief(BaseModel):
    """Grounded answer material for the direct Synthesizer route."""
    synthesis_brief: SynthesisBrief
    answer_draft: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class MemoryRequest(MemorySearchInput):
    direction: str = Field(..., min_length=1)


class Clarification(BaseModel):
    question: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class MemoryCandidate(BaseModel):
    # Project semantic memory is source-backed document knowledge. A chat turn
    # may propose user/tenant candidates only; project publication stays in
    # the document-ingestion workflow.
    scope: Literal["user", "tenant"]
    kind: Literal["fact"] = "fact"
    subject: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    evidence_source_ids: list[str] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class TurnPreflightDecision(BaseModel):
    route: Literal["synthesis", "planner", "recall", "clarify"]
    synthesis_brief: Optional[DirectAnswerBrief] = None
    task_brief: Optional[TaskBrief] = None
    memory_request: Optional[MemoryRequest] = None
    clarification: Optional[Clarification] = None
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    scope_selection: ScopeSelection = Field(default_factory=ScopeSelection)
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_route_payload(self) -> "TurnPreflightDecision":
        required = {
            "synthesis": self.synthesis_brief,
            "planner": self.task_brief,
            "recall": self.memory_request,
            "clarify": self.clarification,
        }
        if required[self.route] is None:
            raise ValueError(f"route={self.route} requires its matching payload")
        if sum(value is not None for value in required.values()) != 1:
            raise ValueError("TurnPreflightDecision must contain exactly one route payload")
        return self


def _canonical_scope_selection(decision: TurnPreflightDecision) -> ScopeSelection:
    selection = decision.scope_selection
    legacy = decision.task_brief
    if legacy is None:
        return selection
    legacy_keys = list(legacy.scope_keys)
    legacy_selection = ScopeSelection(keys=legacy_keys, mode=legacy.scope_mode)
    explicit = bool(selection.keys or selection.mentioned_keys or selection.mode == "replace")
    if not explicit:
        return legacy_selection
    if selection.mode == "replace" and not selection.keys and legacy_selection.keys:
        raise ValueError("conflicting_scope_selection")
    if legacy.scope_mode == "replace" and selection.mode != "replace":
        raise ValueError("conflicting_scope_mode")
    for scope_type in {key.partition(".")[0] for key in legacy_selection.keys}:
        shared = {key for key in selection.keys if key.startswith(f"{scope_type}.")}
        old = {key for key in legacy_selection.keys if key.startswith(f"{scope_type}.")}
        if shared and shared != old:
            raise ValueError("conflicting_scope_selection")
    return ScopeSelection(keys=[*selection.keys, *legacy_selection.keys], mode=selection.mode,
                          mentioned_keys=selection.mentioned_keys, rationale=selection.rationale)


class TurnPreflight:
    """One structured root decision; all memory access remains runtime-owned."""

    # Routing needs the current intent, not an unbounded pasted document or
    # transcript. Preserve both ends: requests often put the actual action
    # after a large quoted payload. The original request remains untouched in
    # PipelineRequest and is handed to planner/synthesizer after routing.
    _MAX_ROUTING_REQUEST_CHARS = 6_000
    _ROUTING_HEAD_CHARS = 4_500

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol) -> None:
        self._session = session
        self._llm = StructuredLLMCall(session=session, llm_client=llm_client)

    async def decide(
        self,
        *,
        user_request: str,
        mechanical_lookup: dict[str, Any],
        facts_context: list[dict[str, Any]] | None = None,
        project_context: dict[str, Any] | None = None,
        chat_context: dict[str, Any] | None = None,
        recent_dialogue: list[dict[str, str]] | None = None,
        continuation: dict[str, Any] | None = None,
        recall_context: dict[str, Any] | None = None,
        chat_id: UUID | None = None,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        sandbox_overrides: dict[str, Any] | None = None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
        trace_parent_entity_id: str | None = None,
        budget_registry: Any = None,
        budget_entity_id: str | None = None,
    ) -> TurnPreflightDecision:
        if self._is_glossary_write_request(user_request):
            return self._glossary_document_decision(user_request=user_request)
        result = await self._llm.invoke(
            role=SystemLLMRoleType.TURN_PREFLIGHT,
            payload={
                "user_request": self._routing_request(user_request),
                "mechanical_lookup": mechanical_lookup,
                # Confirmed user/tenant facts plus small runtime facts (such
                # as the current date) are deliberately passed as a raw
                # projection. Unlike document memory, these are operational
                # context and must be available while resolving pronouns and
                # tool scope.
                "facts_context": list(facts_context or []),
                "project_context": dict(project_context or {}),
                "chat_context": dict(chat_context or {}),
                "recent_dialogue": list(recent_dialogue or []),
                "scope_policy": "team/project focus is initial context, not a ceiling. Select only concrete catalog keys supported by user choice or confirmation, including replies to agent questions. Mere mentions or unconfirmed questions do not change focus. memory_request selects search arguments independently of focus: retain all context teams; choose known projects, [] for outside-project knowledge or [project.all] for common project rules only. project.all is a search selector, never a concrete focus identity.",
                "continuation": continuation or {},
                "recall_context": recall_context,
            },
            schema=TurnPreflightDecision,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            # The lifecycle entity is persisted as an orchestrator with
            # role=turn_preflight. Keep the parent type aligned so the trace
            # projector attaches the LLM call to the visible preflight card.
            trace_parent_entity_type="orchestrator",
            trace_parent_entity_id=trace_parent_entity_id,
            event_sink=event_sink,
            sandbox_overrides=sandbox_overrides,
            budget_registry=budget_registry,
            budget_entity_id=budget_entity_id,
        )
        decision = result.value
        try:
            selection = _canonical_scope_selection(decision)
        except ValueError as exc:
            return TurnPreflightDecision(route="clarify", clarification=Clarification(
                question="Уточните область задачи: указаны противоречащие друг другу наборы скоупов.",
                context={"scope_error": str(exc)},
            ))
        keys = selection.keys
        mentions = selection.mentioned_keys
        # A confirmation such as "yes" may refer to the agent's question in
        # recent_dialogue. Current-message alias matches and initial focus are
        # not a ceiling; validate the resulting identity against the catalog.
        if set(keys).intersection({"team.all", "project.all"}):
            return TurnPreflightDecision(route="clarify", clarification=Clarification(
                question="Укажите конкретную команду или проект: all не используется в фокусе.",
                context={"scope_error": "all_is_not_a_query_scope"},
            ))
        if keys or mentions:
            try:
                await resolve_memory_scopes(self._session, list(dict.fromkeys([*keys, *mentions])))
            except ValueError:
                return TurnPreflightDecision(route="clarify", clarification=Clarification(
                    question="Уточните область задачи: выбранный скоуп отсутствует в активном каталоге.",
                    context={"unknown_scope_keys": list(dict.fromkeys([*keys, *mentions]))},
                ))
        decision = decision.model_copy(update={"scope_selection": selection})
        # Durable user facts are persisted by MemoryWriter after the final
        # answer. They are not agent tasks: no planner executor is allowed to
        # claim that it has written memory. Keep an explicit "remember as a
        # fact" request on the direct path even if a best-effort model routes
        # it to recall or planner.
        if self._is_explicit_fact_memory_write(user_request):
            return self._memory_write_synthesis_decision(
                user_request=user_request,
                memory_candidates=decision.memory_candidates,
            ).model_copy(update={"scope_selection": selection})
        if decision.route == "synthesis" and self._needs_collection_inventory(user_request):
            return TurnPreflightDecision(
                route="planner",
                task_brief=TaskBrief(
                    goal=user_request,
                    direction="Проверить актуальные коллекции и разрешённые пользователю операции с учётом его прав доступа.",
                    expected_result="Подтверждённый список доступных коллекций и операций либо явное ограничение, если проверить их нельзя.",
                ),
                memory_candidates=decision.memory_candidates,
                scope_selection=selection,
            )
        if recall_context is not None and decision.route == "recall":
            raise ValueError("TurnPreflight may request recall only once per turn")
        if decision.route == "planner" and decision.task_brief is not None:
            assignee = self._self_jira_assignee(user_request, facts_context or [])
            if assignee:
                task_brief = decision.task_brief
                entity_hints = list(task_brief.entity_hints)
                if assignee not in entity_hints:
                    entity_hints.append(assignee)
                constraint = (
                    f"Для запроса о собственных задачах Jira обязательно фильтруй по assignee={assignee}."
                )
                constraints = list(task_brief.constraints)
                if constraint not in constraints:
                    constraints.append(constraint)
                decision = decision.model_copy(update={
                    "task_brief": task_brief.model_copy(update={
                        "entity_hints": entity_hints,
                        "constraints": constraints,
                    }),
                })
        return decision

    @staticmethod
    def _self_jira_assignee(
        user_request: str, facts_context: list[dict[str, Any]],
    ) -> str | None:
        """Resolve a self-assignee only from one unambiguous confirmed user fact."""
        text = " ".join(str(user_request or "").lower().split())
        asks_for_own_tasks = bool(re.search(
            r"\b(?:мо\w*|у\s+меня|мне|my|mine|assigned\s+to\s+me)\b", text,
        )) and bool(re.search(r"\b(?:задач\w*|тикет\w*|issue\w*|ticket\w*)\b", text))
        mentions_jira = bool(re.search(r"\bjira\b", text))
        if not (asks_for_own_tasks and mentions_jira):
            return None

        accepted_subjects = {
            "учетная запись", "учётная запись", "логин", "jira username",
            "username", "user.jira.username",
        }
        candidates = {
            str(item.get("value") or "").strip()
            for item in facts_context
            if isinstance(item, dict)
            and item.get("scope") == "user"
            and item.get("kind") == "fact"
            and str(item.get("subject") or "").strip().lower() in accepted_subjects
            and re.fullmatch(r"[A-Za-z0-9._-]{2,80}", str(item.get("value") or "").strip())
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    @staticmethod
    def _needs_collection_inventory(user_request: str) -> bool:
        """A terminology lookup cannot establish current collection access."""
        text = " ".join((user_request or "").lower().split())
        if not re.search(r"\bколлекци\w*\b|\bcollections?\b", text):
            return False
        return bool(re.search(
            r"\b(?:доступ\w*|разреш\w*|мо[ийяе]|наш\w*|могу|можем|операци\w*|оперир\w*|"
            r"available|accessible|access|allowed|my|our|can|permissions?)\b",
            text,
        ))

    @classmethod
    def _routing_request(cls, user_request: str) -> str:
        text = str(user_request or "")
        if len(text) <= cls._MAX_ROUTING_REQUEST_CHARS:
            return text
        tail_size = cls._MAX_ROUTING_REQUEST_CHARS - cls._ROUTING_HEAD_CHARS
        return (
            f"{text[:cls._ROUTING_HEAD_CHARS]}\n\n"
            "[Середина пользовательского сообщения опущена только для маршрутизации; "
            "при продолжении исходный текст доступен следующей роли.]\n\n"
            f"{text[-tail_size:]}"
        )

    @staticmethod
    def _is_explicit_fact_memory_write(user_request: str) -> bool:
        text = " ".join((user_request or "").lower().split())
        return bool(re.search(
            r"(?:запомни(?:те)?|сохрани(?:те)?|remember|save)"
            r".{0,100}(?:как\s+факт|as\s+a\s+fact)",
            text,
        ))

    @staticmethod
    def _is_glossary_write_request(user_request: str) -> bool:
        text = " ".join((user_request or "").lower().split())
        action = r"(?:добав(?:ь|ьте)|внеси(?:те)?|сохрани(?:ть|те)|запомни(?:ть|те)|add|save)"
        glossary = r"(?:глоссар|glossar)"
        return bool(re.search(rf"{action}.{{0,120}}{glossary}|{glossary}.{{0,120}}{action}", text))

    @staticmethod
    def _glossary_document_decision(
        *, user_request: str,
    ) -> TurnPreflightDecision:
        return TurnPreflightDecision(
            route="synthesis",
            synthesis_brief=DirectAnswerBrief(
                synthesis_brief=SynthesisBrief(
                    user_question=user_request,
                    planned_work="Объяснить документный порядок публикации определения.",
                    purpose="Указать, что глоссарий пополняется после изучения и утверждения документа.",
                    answer_requirements=(
                        "Предложить загрузить документ с определением для изучения и проверки. "
                        "Не утверждать, что термин добавлен или принят на публикацию."
                    ),
                ),
                answer_draft="Загрузите документ с определением. После изучения и утверждения термина он появится в глоссарии.",
            ),
        )

    @staticmethod
    def _memory_write_synthesis_decision(
        *, user_request: str, memory_candidates: list[MemoryCandidate],
    ) -> TurnPreflightDecision:
        return TurnPreflightDecision(
            route="synthesis",
            synthesis_brief=DirectAnswerBrief(
                synthesis_brief=SynthesisBrief(
                    user_question=user_request,
                    planned_work="Передать явно указанный пользователем факт в стандартный writeback памяти.",
                    purpose="Подтвердить принятие факта без выдумывания результата записи.",
                    answer_requirements=(
                        "Кратко подтвердить, что формулировка принята как кандидат памяти; "
                        "не утверждать, что запись уже завершена до runtime writeback."
                    ),
                ),
                answer_draft=(
                    "Формулировка принята как кандидат для сохранения в памяти. "
                    "Она будет обработана стандартным writeback этого turn."
                ),
            ),
            memory_candidates=memory_candidates,
        )
