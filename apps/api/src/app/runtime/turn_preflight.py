"""Root turn routing before planner or synthesizer."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.interaction import InteractionQuestion, interaction_from_context
from app.runtime.root_route_policy import RootRouteRecommendation
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import SynthesisBrief
from app.services.memory_scope_catalog import resolve_memory_scopes
from app.runtime.memory.effective_scope import ScopeSelection
from app.agents.context import ToolContext
from app.runtime.memory.role_tools import MemoryToolCall, RoleMemoryTools
from app.runtime.input_builders import compact_memory_tool_records
from app.runtime.datastore_context import build_datastore, file_metadata
from app.runtime.contracts import AttachmentContext
from app.runtime.run_context import ResolvedReference


class TaskBrief(BaseModel):
    goal: str = Field(..., min_length=1)
    project_hints: list[str] = Field(default_factory=list, description="Project names/keys from the user or confirmed facts, including external projects absent from the memory catalog.")
    scope_keys: list[str] = Field(default_factory=list, description="Exact catalog scope slugs only. Empty inherit preserves focus.")
    scope_mode: Literal["inherit", "replace"] = "inherit"
    entity_hints: list[str] = Field(default_factory=list)
    direction: str = Field(..., min_length=1)
    constraints: list[str] = Field(default_factory=list)
    expected_result: str = Field(..., min_length=1)
    resolved_references: list[ResolvedReference] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    message_refs: list[str] = Field(default_factory=list)
    synthesis_brief: SynthesisBrief | None = None
    model_config = {"extra": "forbid"}


class DirectAnswerBrief(BaseModel):
    """Grounded answer material for the direct Synthesizer route."""
    synthesis_brief: SynthesisBrief
    answer_draft: str = Field(..., min_length=1)
    model_config = {"extra": "forbid"}


class Clarification(InteractionQuestion):
    question: str = Field(..., min_length=1)
    direct_answer_reason: Optional[str] = Field(
        default=None, min_length=1,
        description="Why the answer after this single choice can be synthesized solely from existing input, without search, verification, tools or actions. Otherwise route to planner.",
    )
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


class ArtifactDescription(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str
    description: str = Field(min_length=1, max_length=600)


class TurnPreflightDecision(BaseModel):
    artifact_descriptions: list[ArtifactDescription] = Field(default_factory=list)
    route: Literal["synthesis", "planner", "tool_call", "clarify"]
    synthesis_brief: Optional[DirectAnswerBrief] = None
    task_brief: Optional[TaskBrief] = None
    tool_call: Optional[MemoryToolCall] = None
    _memory_tool_results: list[dict[str, Any]] = PrivateAttr(default_factory=list)
    _proposed_route: Optional[str] = PrivateAttr(default=None)
    clarification: Optional[Clarification] = None
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    scope_selection: ScopeSelection = Field(default_factory=ScopeSelection)
    model_config = {"extra": "forbid"}

    @property
    def memory_tool_results(self) -> list[dict[str, Any]]:
        return self._memory_tool_results

    @model_validator(mode="after")
    def validate_route_payload(self) -> "TurnPreflightDecision":
        required = {
            "synthesis": self.synthesis_brief,
            "planner": self.task_brief,
            "tool_call": self.tool_call,
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
    if selection.keys and legacy_keys and set(selection.keys) != set(legacy_keys):
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
        recent_dialogue: list[dict[str, Any]] | None = None,
        attachments: list[AttachmentContext] | None = None,
        continuation: dict[str, Any] | None = None,
        routing_recommendation: RootRouteRecommendation | None = None,
        ctx: ToolContext | None = None,
        chat_id: UUID | None = None,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        sandbox_overrides: dict[str, Any] | None = None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
        trace_parent_entity_id: str | None = None,
        budget_registry: Any = None,
        budget_entity_id: str | None = None,
    ) -> TurnPreflightDecision:
        # Old checkpoints may still mix chat/project snapshots into memory.
        facts_context = [item for item in facts_context or []
                         if item.get("type") not in {"chat_context", "project_context"}]
        if self._is_glossary_write_request(user_request):
            return self._glossary_document_decision(user_request=user_request)
        if event_sink:
            await event_sink(RuntimeEvent.status(
                "memory_context_used",
                entity_type="orchestrator", entity_id=trace_parent_entity_id,
                memory_context=[*(facts_context or []), mechanical_lookup],
            ))
        tools = RoleMemoryTools(session=self._session, ctx=ctx)
        descriptors = await tools.descriptors()
        resumed = interaction_from_context((continuation or {}).get("paused_context"))
        checkpoint_results = list(resumed.checkpoint.get("memory_tool_results") or []) if resumed else []
        # File contents are an access-controlled read result. A paused
        # checkpoint can outlive the artifact grant, so require a fresh tool
        # execution after resume instead of replaying cached content to the LLM.
        tool_results: list[dict[str, Any]] = [
            item for item in checkpoint_results
            if isinstance(item, dict) and item.get("tool") not in {
                "file.read", "file.data.read", "file.data.search",
            }
        ]
        available_artifacts = file_metadata([item.model_dump(mode="json") for item in attachments or []])
        from app.runtime.prompt_projections import preflight_context
        dialogue = list(recent_dialogue or [])
        if dialogue and dialogue[-1].get("role") == "user" and dialogue[-1].get("content") == user_request:
            dialogue = dialogue[:-1]
        prompt_project, prompt_chat = preflight_context(dict(project_context or {}), dict(chat_context or {}),
                                                       dialogue=dialogue, user_request=user_request)
        for _ in range(RoleMemoryTools.MAX_CALLS + 1):
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
                    "project_context": prompt_project,
                    "chat_context": prompt_chat,
                    "recent_dialogue": dialogue,
                    "routing_recommendation": (
                        routing_recommendation.model_dump(mode="json")
                        if routing_recommendation is not None else None
                    ),
                    "datastore": build_datastore(files=available_artifacts),
                    "continuation": continuation or {},
                    "available_tools": [{key: value for key, value in descriptor.items() if key != "input_schema"}
                                        for descriptor in descriptors],
                    "memory_tool_results": compact_memory_tool_records(tool_results),
                    "memory_tool_calls_remaining": RoleMemoryTools.MAX_CALLS - len(tool_results),
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
            decision._proposed_route = decision.route
            if (decision.route == "clarify" and len(available_artifacts) == 1
                    and re.search(r"прикреп|загруз|attach|upload", decision.clarification.question, re.IGNORECASE)):
                decision = TurnPreflightDecision(route="tool_call", tool_call=MemoryToolCall(
                    tool="file.read", arguments={"artifact_id": available_artifacts[0]["artifact_id"]}))

            if decision.route == "clarify" and self._repeats_answered_question(
                decision.clarification.question, user_request, continuation or {},
            ):
                decision = self._planner_handoff(str((continuation or {}).get("original_goal") or user_request), decision,
                    reason="Предложенное уточнение повторяет исходный запрос или уже отвеченный вопрос. Продолжи работу с имеющимися данными и ответами пользователя.")
            if decision.route != "tool_call":
                break
            if len(tool_results) >= RoleMemoryTools.MAX_CALLS:
                decision = self._planner_handoff(user_request, decision,
                    reason="Бюджет поиска памяти исчерпан; используй найденный контекст и продолжи работу.")
                break
            selection = _canonical_scope_selection(decision)
            current_keys = set(((project_context or {}).get("scope_context") or {}).get("keys") or [])
            if (selection.keys or selection.mode == "replace") and set(selection.keys) != current_keys:
                # Pipeline applies the validated focus before invoking planner.
                # Searching now would use the previous chat scope and attach
                # evidence to a different selection in the final decision.
                decision = self._planner_handoff(user_request, decision, selection=selection,
                    reason="Сначала примени выбранные scope, затем выполни поиск по ним.")
                break
            assert decision.tool_call is not None
            tool_results.append(await tools.execute(decision.tool_call, actor="turn_preflight",
                parent_type="orchestrator", parent_id=trace_parent_entity_id, event_sink=event_sink))
        decision._memory_tool_results = tool_results

        try:
            selection = _canonical_scope_selection(decision)
        except ValueError:
            return self._planner_handoff(user_request, decision, reason="Не удалось согласовать выбор области памяти; исходный фокус сохранён.")
        keys = selection.keys
        mentions = selection.mentioned_keys
        # A confirmation such as "yes" may refer to the agent's question in
        # recent_dialogue. Current-message alias matches and initial focus are
        # not a ceiling; validate the resulting identity against the catalog.
        if keys or mentions:
            try:
                await resolve_memory_scopes(self._session, list(dict.fromkeys([*keys, *mentions])))
            except ValueError:
                return self._planner_handoff(user_request, decision, reason="Выбор области памяти не разрешён по активному каталогу; исходный фокус сохранён. Установи параметры работы по доступным источникам.")
        decision = decision.model_copy(update={"scope_selection": selection})
        current_keys = set(((project_context or {}).get("scope_context") or {}).get("keys") or [])
        if tool_results and decision.route == "synthesis" and (keys or selection.mode == "replace") and set(keys) != current_keys:
            routed = self._planner_handoff(user_request, decision, selection=selection,
                reason="Найденные фрагменты относятся к прежним scope. Выполни поиск в выбранных scope перед ответом.")
            routed._proposed_route = decision._proposed_route
            routed._memory_tool_results = tool_results
            return routed
        # Durable user facts are persisted by MemoryWriter after the final
        # answer. They are not agent tasks: no planner executor is allowed to
        # claim that it has written memory. Keep an explicit "remember as a
        # fact" request on the direct path even if a best-effort model routes
        # it to tool_call or planner.
        if self._is_explicit_fact_memory_write(user_request) and not self._has_non_memory_intent(user_request):
            routed = self._memory_write_synthesis_decision(
                user_request=user_request,
                memory_candidates=decision.memory_candidates,
            ).model_copy(update={"scope_selection": selection})
            routed._proposed_route = decision._proposed_route
            routed._memory_tool_results = tool_results
            return routed
        if decision.route == "clarify" and not str(decision.clarification.direct_answer_reason or "").strip():
            return self._planner_handoff(user_request, decision, reason="Предварительное уточнение: " + decision.clarification.question,
                                         selection=selection)
        if decision.route in {"synthesis", "clarify"} and self._needs_collection_inventory(user_request):
            routed = TurnPreflightDecision(
                route="planner",
                task_brief=TaskBrief(
                    goal=user_request,
                    direction="Проверить актуальные коллекции и разрешённые пользователю операции с учётом его прав доступа.",
                    expected_result="Подтверждённый список доступных коллекций и операций либо явное ограничение, если проверить их нельзя.",
                ),
                memory_candidates=decision.memory_candidates,
                scope_selection=selection,
            )
            routed._memory_tool_results = tool_results
            routed._proposed_route = decision._proposed_route
            return routed
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
    def _repeats_answered_question(question: str, user_request: str, continuation: dict[str, Any]) -> bool:
        def normalized(value: Any) -> str:
            return re.sub(r"[^\w]+", " ", str(value or "").casefold()).strip()
        candidates = [user_request, continuation.get("original_goal")]
        candidates.extend(item.get("question") for item in continuation.get("clarification_history", [])
                          if isinstance(item, dict) and "answer" in item)
        if continuation.get("resume_action") == "input" and continuation.get("user_response"):
            candidates.extend((continuation.get(key) or {}).get("question") for key in ("paused_action", "paused_context"))
        return bool(normalized(question)) and normalized(question) in {normalized(value) for value in candidates if value}

    @staticmethod
    def _planner_handoff(
        user_request: str, decision: TurnPreflightDecision, *, reason: str,
        selection: ScopeSelection | None = None,
    ) -> TurnPreflightDecision:
        """Model scope mistakes are planning context, not questions for the user."""
        brief = decision.task_brief or TaskBrief(
            goal=user_request, direction="Разобраться в запросе по доступным источникам и выполнить необходимую работу.",
            expected_result="Ответ на исходный запрос с проверенными данными или обоснованным адресным уточнением.",
        )
        selected = selection or ScopeSelection()
        routed = TurnPreflightDecision(
            route="planner", scope_selection=selected, memory_candidates=decision.memory_candidates,
            task_brief=brief.model_copy(update={
                "goal": user_request, "scope_keys": selected.keys, "scope_mode": selected.mode,
                "constraints": [*brief.constraints, reason],
            }),
        )
        routed._memory_tool_results = decision.memory_tool_results
        routed._proposed_route = decision._proposed_route
        routed._reroute_reason = reason
        return routed

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
    def _has_non_memory_intent(user_request: str) -> bool:
        text = " ".join((user_request or "").lower().split())
        text = re.sub(
            r"(?:запомни(?:те)?|сохрани(?:те)?|remember|save).{0,120}(?:как\s+факт|as\s+a\s+fact)",
            " ", text,
        )
        return bool(re.search(
            r"(?:покажи|найди|проверь|создай|удали|обнови|отправь|получи|сравни|выполни|\bshow\b|\bfind\b|\bcheck\b|\bcreate\b|\bdelete\b|\bupdate\b|\bsend\b|\bfetch\b|\bcompare\b)",
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
