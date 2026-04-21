"""Targeted runtime coverage — validator, AgentExecutor helpers, Planner.

Post-M5 rewrite: `TurnSummarizer` tests dropped (summarizer removed —
its role is now owned by `SummaryCompactor` which has its own tests in
`test_memory_helpers.py`). Validator tests now cover the new
`DIRECT_ANSWER` and `CLARIFY` kinds.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.runtime.events import RuntimeEventType as LegacyEventType
from app.runtime.agent_executor import AgentExecutor
from app.runtime.contracts import NextStep, NextStepKind
from app.runtime.events import RuntimeEventType
from app.runtime.llm.structured import StructuredCallError
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.planner.planner import Planner, PlannerLLMOutput
from app.runtime.planner.validator import validate_next_step


def _memory(*, can_finalize: bool = True) -> WorkingMemory:
    mem = WorkingMemory(run_id=uuid4(), goal="goal")
    if not can_finalize:
        mem.outline = {"phases": [{"phase_id": "must-do", "must_do": True}]}
    return mem


def test_validator_call_agent_missing_slug_errors():
    assert validate_next_step(
        NextStep(kind=NextStepKind.CALL_AGENT, rationale="r"),
        allowed_agents=["analyst"],
        memory=_memory(),
    ) == "call_agent step missing agent_slug"


def test_validator_call_agent_not_in_allowed_list_errors():
    err = validate_next_step(
        NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops"),
        allowed_agents=["analyst"],
        memory=_memory(),
    )
    assert err is not None and "not in the allowed list" in err


def test_validator_clarify_and_ask_user_require_question():
    # ASK_USER with empty question
    assert validate_next_step(
        NextStep(kind=NextStepKind.ASK_USER, rationale="r", question=""),
        allowed_agents=[],
        memory=_memory(),
    ) == "ask_user step missing question"
    # CLARIFY with empty question (new kind)
    assert validate_next_step(
        NextStep(kind=NextStepKind.CLARIFY, rationale="r", question=""),
        allowed_agents=[],
        memory=_memory(),
    ) == "clarify step missing question"


def test_validator_direct_answer_requires_final_answer():
    assert validate_next_step(
        NextStep(kind=NextStepKind.DIRECT_ANSWER, rationale="r", final_answer=""),
        allowed_agents=[],
        memory=_memory(),
    ) == "direct_answer step missing final_answer"
    # happy
    assert validate_next_step(
        NextStep(kind=NextStepKind.DIRECT_ANSWER, rationale="r", final_answer="hi"),
        allowed_agents=[],
        memory=_memory(),
    ) is None


def test_validator_final_and_abort_constraints():
    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer=""),
        allowed_agents=[],
        memory=_memory(),
    ) == "final step missing final_answer"

    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer="ok"),
        allowed_agents=[],
        memory=_memory(can_finalize=False),
    ) == "final step blocked: must_do phase is not complete yet"

    assert validate_next_step(
        NextStep(kind=NextStepKind.ABORT, rationale=" "),
        allowed_agents=[],
        memory=_memory(),
    ) == "abort step missing rationale"

    assert validate_next_step(
        NextStep(kind=NextStepKind.ABORT, rationale="stop"),
        allowed_agents=[],
        memory=_memory(),
    ) is None


def test_agent_executor_helper_paths():
    legacy_status = SimpleNamespace(type=LegacyEventType.STATUS, data={"stage": "x"})
    translated = AgentExecutor._translate(legacy_status)  # noqa: SLF001
    assert translated is not None
    assert translated.type == RuntimeEventType.STATUS

    legacy_thinking = SimpleNamespace(type=LegacyEventType.THINKING, data={"step": 2})
    translated_thinking = AgentExecutor._translate(legacy_thinking)  # noqa: SLF001
    assert translated_thinking is not None
    assert translated_thinking.type == RuntimeEventType.STATUS

    legacy_final = SimpleNamespace(type=LegacyEventType.FINAL, data={"content": "x"})
    assert AgentExecutor._translate(legacy_final) is None  # noqa: SLF001

    outer = [{"role": "system", "content": "x"}, {"role": "user", "content": "old"}]
    step = NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops", agent_input={"query": "new"})
    messages = AgentExecutor._build_sub_messages(outer, step, _memory())  # noqa: SLF001
    assert messages[-1] == {"role": "user", "content": "new"}
    assert all(m["role"] != "system" for m in messages)

    facts = AgentExecutor._extract_facts(  # noqa: SLF001
        "  * first useful line\nshort\nsecond useful line",
        [{"title": "Source A"}],
    )
    assert "first useful line" in facts[0]
    assert any(f.startswith("source: Source A") for f in facts)

    assert AgentExecutor._count_operations(SimpleNamespace(resolved_operations=[1, 2])) == 2  # noqa: SLF001


@pytest.mark.asyncio
async def test_planner_retry_and_fallback_paths():
    planner = Planner(session=AsyncMock(), llm_client=AsyncMock())

    planner.llm.invoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                value=PlannerLLMOutput(
                    kind="call_agent",
                    rationale="first",
                    agent_slug="forbidden",
                    agent_input={},
                )
            ),
            SimpleNamespace(
                value=PlannerLLMOutput(
                    kind="call_agent",
                    rationale="second",
                    agent_slug="analyst",
                    agent_input={"query": "q"},
                )
            ),
        ]
    )

    step = await planner.next_step(
        memory=_memory(),
        available_agents=[{"slug": "analyst", "description": "A"}],
    )
    assert step.kind == NextStepKind.CALL_AGENT
    assert step.agent_slug == "analyst"

    planner.llm.invoke = AsyncMock(side_effect=StructuredCallError("llm down"))
    fallback = await planner.next_step(memory=_memory(), available_agents=[])
    assert fallback.kind == NextStepKind.ABORT


@pytest.mark.asyncio
async def test_planner_emits_direct_answer_kind_when_llm_returns_one():
    """New kind wiring: planner's LLM → DIRECT_ANSWER NextStep."""
    planner = Planner(session=AsyncMock(), llm_client=AsyncMock())
    planner.llm.invoke = AsyncMock(
        return_value=SimpleNamespace(
            value=PlannerLLMOutput(
                kind="direct_answer",
                rationale="small-talk",
                final_answer="Привет! Чем могу помочь?",
            )
        )
    )

    step = await planner.next_step(memory=_memory(), available_agents=[])
    assert step.kind == NextStepKind.DIRECT_ANSWER
    assert step.final_answer == "Привет! Чем могу помочь?"
