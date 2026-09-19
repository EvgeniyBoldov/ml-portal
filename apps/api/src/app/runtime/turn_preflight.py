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


class TaskBrief(BaseModel):
    goal: str = Field(..., min_length=1)
    project_hints: list[str] = Field(default_factory=list)
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


class MemoryRequest(BaseModel):
    project_keys: list[str] = Field(default_factory=list)
    direction: str = Field(..., min_length=1)
    kinds: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    scopes: list[Literal["glossary", "project", "global"]] = Field(default_factory=lambda: ["glossary", "project", "global"])
    query: str = Field(..., min_length=1)
    limit: int = Field(default=8, ge=1, le=12)
    model_config = {"extra": "forbid"}


class Clarification(BaseModel):
    question: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    model_config = {"extra": "forbid"}


class MemoryCandidate(BaseModel):
    # Project semantic memory is source-backed document knowledge. A chat turn
    # may propose user/tenant candidates only; project publication stays in
    # the document-ingestion workflow.
    scope: Literal["user", "tenant"]
    kind: Literal["fact", "glossary"] = "fact"
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


class TurnPreflight:
    """One structured root decision; all memory access remains runtime-owned."""

    # Routing needs the current intent, not an unbounded pasted document or
    # transcript. Preserve both ends: requests often put the actual action
    # after a large quoted payload. The original request remains untouched in
    # PipelineRequest and is handed to planner/synthesizer after routing.
    _MAX_ROUTING_REQUEST_CHARS = 6_000
    _ROUTING_HEAD_CHARS = 4_500

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol) -> None:
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
        # Durable user facts are persisted by MemoryWriter after the final
        # answer. They are not agent tasks: no planner executor is allowed to
        # claim that it has written memory. Keep an explicit "remember as a
        # fact" request on the direct path even if a best-effort model routes
        # it to recall or planner.
        if self._is_explicit_fact_memory_write(user_request):
            return self._memory_write_synthesis_decision(
                user_request=user_request,
                memory_candidates=decision.memory_candidates,
            )
        # Writeback intentionally happens after the user-facing answer. A
        # direct route with glossary candidates may acknowledge receipt, but
        # cannot truthfully claim that publication has completed yet.
        if (
            decision.route == "synthesis"
            and decision.memory_candidates
            and self._is_glossary_write_request(user_request)
        ):
            return self._glossary_write_synthesis_decision(
                user_request=user_request,
                memory_candidates=decision.memory_candidates,
            )
        if recall_context is not None and decision.route == "recall":
            raise ValueError("TurnPreflight may request recall only once per turn")
        return decision

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
        return bool(re.search(
            r"(?:добав(?:ь|ьте)|сохрани(?:ть|те)|запомни(?:ть|те)|add|save)"
            r".{0,120}(?:глоссар|glossar)",
            text,
        ))

    @staticmethod
    def _glossary_write_synthesis_decision(
        *, user_request: str, memory_candidates: list[MemoryCandidate],
    ) -> TurnPreflightDecision:
        return TurnPreflightDecision(
            route="synthesis",
            synthesis_brief=DirectAnswerBrief(
                synthesis_brief=SynthesisBrief(
                    user_question=user_request,
                    planned_work="Передать предоставленные термины на проверку перед добавлением в глоссарий.",
                    purpose="Подтвердить принятие терминов без заявления о завершённой записи.",
                    answer_requirements=(
                        "Кратко подтвердить, что термины приняты для проверки; "
                        "не утверждать, что они уже добавлены или доступны в глоссарии."
                    ),
                ),
                answer_draft="Термины приняты для проверки перед добавлением в глоссарий.",
            ),
            memory_candidates=memory_candidates,
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
