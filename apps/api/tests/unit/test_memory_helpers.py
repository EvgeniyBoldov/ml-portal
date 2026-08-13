"""Unit tests for FactExtractor and SummaryCompactor.

The LLM call itself is delegated to `StructuredLLMCall.invoke`. We
patch that method and focus on:

  * FactExtractor: post-validation rules (scope filtering, owner id
    sanity, clipping, cap) and fail-safe behaviour on exceptions.
  * SummaryCompactor: fallback path preserves prior state and bumps
    the turn number; happy path clips oversized lists/maps.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope
from app.runtime.llm.structured import (
    StructuredCallError,
    StructuredCallResult,
)
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_extractor import (
    AgentResultSnippet,
    FactExtractor,
    _resolve_fact_policy,
    _LLMFactCandidate,
    _LLMFactOutput,
)
from app.runtime.memory.summary_compactor import (
    SummaryCompactor,
    _resolve_summary_policy,
    _merge_summary,
    _LLMSummaryOutput,
)
from app.runtime.memory.preparer import MemoryPreparer, _PreparationOutput
from app.runtime.memory.dto import FactDTO
from app.models.memory import FactSource


def _llm_result(value):
    return StructuredCallResult(
        value=value,
        trace_id=None,
        raw_response="",
        duration_ms=1,
        model="test",
        request_messages=[],
        request_params={},
    )


# ============================================================= FactExtractor


@pytest.fixture
def extractor() -> FactExtractor:
    ex = FactExtractor(session=AsyncMock(), llm_client=AsyncMock())
    return ex


@pytest.mark.asyncio
async def test_fact_extractor_maps_valid_candidates_to_dtos(extractor):
    uid = uuid4()
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="user", subject="user.name",
                        value="Anna", confidence=0.9,
                    ),
                    _LLMFactCandidate(
                        scope="user", subject="user.stack",
                        value="Cisco IOS", confidence=0.8,
                    ),
                ]
            )
        )
    )

    facts = await extractor.extract(
        user_message="My name is Anna and I work with Cisco IOS",
        agent_results=[],
        known_facts=[],
        user_id=uid,
    )

    assert len(facts) == 2
    assert all(f.scope == FactScope.USER for f in facts)
    assert all(f.owner_id is None for f in facts)  # ownership is assigned by reconciler
    assert {f.subject for f in facts} == {"user.name", "user.stack"}


@pytest.mark.asyncio
async def test_fact_extractor_drops_unknown_scope(extractor):
    uid = uuid4()
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="global", subject="x", value="y", confidence=1.0
                    ),
                    _LLMFactCandidate(
                        scope="user", subject="user.name",
                        value="Boris", confidence=1.0,
                    ),
                ]
            )
        )
    )
    facts = await extractor.extract(
        user_message="Boris", agent_results=[], known_facts=[], user_id=uid,
    )
    assert len(facts) == 1
    assert facts[0].subject == "user.name"


@pytest.mark.asyncio
async def test_fact_extractor_drops_user_scope_without_user_id(extractor):
    """A user-scoped fact with no user_id is nonsense — drop it."""
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="user", subject="user.name",
                        value="Anna", confidence=1.0,
                    )
                ]
            )
        )
    )
    facts = await extractor.extract(
        user_message="Anna", agent_results=[], known_facts=[], user_id=None,
    )
    assert facts == []


@pytest.mark.asyncio
async def test_fact_extractor_clips_overlong_value(extractor):
    uid = uuid4()
    huge = "x" * 10_000
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="user", subject="user.note",
                        value=huge, confidence=1.0,
                    )
                ]
            )
        )
    )
    facts = await extractor.extract(
        user_message=huge, agent_results=[], known_facts=[], user_id=uid,
    )
    assert len(facts) == 1
    assert len(facts[0].value) <= 500


@pytest.mark.asyncio
async def test_fact_extractor_caps_at_max_per_turn(extractor):
    uid = uuid4()
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="user", subject=f"user.k{i}",
                        value=f"v{i}", confidence=1.0,
                    )
                    for i in range(20)
                ]
            )
        )
    )
    facts = await extractor.extract(
        user_message=" ".join(f"v{i}" for i in range(20)), agent_results=[], known_facts=[], user_id=uid,
    )
    assert len(facts) == 8


@pytest.mark.asyncio
async def test_fact_extractor_returns_empty_on_llm_error(extractor):
    """Extractor must never raise — a failed LLM call means no facts this turn."""
    extractor._structured.invoke = AsyncMock(
        side_effect=StructuredCallError("boom")
    )
    facts = await extractor.extract(
        user_message="x", agent_results=[], known_facts=[], user_id=uuid4(),
    )
    assert facts == []


@pytest.mark.asyncio
async def test_fact_extractor_returns_empty_on_unexpected_exception(extractor):
    extractor._structured.invoke = AsyncMock(
        side_effect=RuntimeError("unexpected")
    )
    facts = await extractor.extract(
        user_message="x", agent_results=[], known_facts=[], user_id=uuid4(),
    )
    assert facts == []


def test_fact_extractor_policy_merges_role_and_sandbox():
    policy = _resolve_fact_policy(
        {"max_facts_per_turn": 3, "confidence_min": 0.7},
        {"fact_extractor": {"max_facts_per_turn": 5}},
    )
    # sandbox override wins over role extras
    assert policy["max_facts_per_turn"] == 5
    assert policy["confidence_min"] == 0.7


@pytest.mark.asyncio
async def test_fact_extractor_rejects_agent_summary_without_primary_evidence(extractor):
    uid = uuid4()
    extractor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMFactOutput(
                facts=[
                    _LLMFactCandidate(
                        scope="user",
                        subject="preferred vendor",
                        value="juniper",
                        confidence=0.95,
                    )
                ]
            )
        )
    )
    facts = await extractor.extract(
        user_message="",
        agent_results=[AgentResultSnippet(agent="viewer", summary="Preferred vendor: juniper", success=True)],
        known_facts=[],
        user_id=uid,
    )
    assert facts == []


@pytest.mark.asyncio
async def test_memory_preparer_selects_only_llm_indexed_context() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(return_value=_llm_result(
        _PreparationOutput(fact_indexes=[1], project_indexes=[0], ambiguities=["Нема может означать два проекта"])
    ))
    facts = [
        FactDTO(scope=FactScope.USER, subject="user.role", value="network engineer", source=FactSource.USER_UTTERANCE),
        FactDTO(scope=FactScope.TENANT, subject="tenant.standard", value="ITIL", source=FactSource.USER_UTTERANCE),
    ]
    result = await preparer.prepare(
        request_text="Нужна заявка для Немы", facts=facts,
        project_glossary=[{"id": uuid4(), "key": "nemesis", "name": "Немезида", "aliases": ["Нема"]}],
        user_id=uuid4(), tenant_id=uuid4(), chat_id=None, sandbox_overrides=None,
    )

    assert result.fallback is False
    assert result.items[0]["subject"] == "tenant.standard"
    assert result.items[1]["key"] == "nemesis"
    assert result.ambiguities == ["Нема может означать два проекта"]


@pytest.mark.asyncio
async def test_memory_preparer_degrades_to_empty_context() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(side_effect=RuntimeError("offline"))

    result = await preparer.prepare(
        request_text="test", facts=[], project_glossary=[], user_id=None,
        tenant_id=None, chat_id=None, sandbox_overrides=None,
    )

    assert result.fallback is True
    assert result.items == []


@pytest.mark.asyncio
async def test_fact_extractor_keeps_project_aliases_with_evidenced_project_fact(extractor) -> None:
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(
        _LLMFactOutput(facts=[_LLMFactCandidate(
            scope="project", project_key="nemesis", project_aliases=["Нема", "нема"],
            subject="project.name", value="Немезида", confidence=1.0,
        )])
    ))

    facts = await extractor.extract(
        user_message="Для проекта Немезида, или Нема, нужна сеть", known_facts=[],
        user_id=uuid4(), tenant_id=uuid4(),
    )

    assert len(facts) == 1
    assert facts[0].metadata["project_aliases"] == ["Нема"]


# ============================================================ SummaryCompactor


@pytest.fixture
def compactor() -> SummaryCompactor:
    return SummaryCompactor(session=AsyncMock(), llm_client=AsyncMock())


@pytest.mark.asyncio
async def test_summary_compactor_happy_path_clips_and_sets_turn(compactor):
    chat_id = uuid4()
    prev = SummaryDTO(chat_id=chat_id, goals=["old"], last_updated_turn=1)
    compactor._structured.invoke = AsyncMock(
        return_value=_llm_result(
            _LLMSummaryOutput(
                goals=[f"goal{i}" for i in range(20)],
                done=["d1", "d1", "d2"],            # dup should be removed
                entities={"incident": "INC-1"},
                open_questions=[],
            )
        )
    )

    out = await compactor.compact(
        previous=prev,
        user_message="hi",
        assistant_final="hello",
        agent_results=[],
        turn_number=2,
        chat_id=chat_id,
    )

    assert out.chat_id == chat_id
    assert out.last_updated_turn == 2
    assert len(out.goals) == 5            # capped at MAX_GOALS
    assert out.done == ["d1", "d2"]       # dedup
    assert out.entities == {"incident": "INC-1"}


@pytest.mark.asyncio
async def test_summary_compactor_preserves_raw_tail_from_previous(compactor):
    """raw_tail is maintained by the writer, not the LLM — the compactor
    must carry it forward verbatim even on a successful LLM call."""
    chat_id = uuid4()
    prev = SummaryDTO(
        chat_id=chat_id,
        raw_tail="user: hi\nassistant: hello",
        last_updated_turn=1,
    )
    compactor._structured.invoke = AsyncMock(
        return_value=_llm_result(_LLMSummaryOutput())
    )
    out = await compactor.compact(
        previous=prev, user_message="", assistant_final="",
        agent_results=[], turn_number=2,
    )
    assert out.raw_tail == "user: hi\nassistant: hello"


@pytest.mark.asyncio
async def test_summary_compactor_fallback_keeps_prior_fields(compactor):
    """LLM failure → return a copy of previous with only last_updated_turn bumped."""
    chat_id = uuid4()
    prev = SummaryDTO(
        chat_id=chat_id,
        goals=["g1"], done=["d1"], entities={"k": "v"},
        open_questions=["q1"], raw_tail="tail", last_updated_turn=3,
    )
    compactor._structured.invoke = AsyncMock(
        side_effect=StructuredCallError("boom")
    )
    out = await compactor.compact(
        previous=prev, user_message="", assistant_final="",
        agent_results=[], turn_number=4,
    )
    assert out.goals == ["g1"]
    assert out.done == ["d1"]
    assert out.entities == {"k": "v"}
    assert out.open_questions == ["q1"]
    assert out.raw_tail == "tail"
    assert out.last_updated_turn == 4


@pytest.mark.asyncio
async def test_summary_compactor_fallback_on_unexpected_exception(compactor):
    chat_id = uuid4()
    prev = SummaryDTO(chat_id=chat_id, last_updated_turn=0)
    compactor._structured.invoke = AsyncMock(side_effect=RuntimeError("x"))
    out = await compactor.compact(
        previous=prev, user_message="", assistant_final="",
        agent_results=[], turn_number=1,
    )
    assert out.last_updated_turn == 1


def test_summary_compactor_policy_merges_role_and_sandbox():
    policy = _resolve_summary_policy(
        {"max_goals": 2, "max_item_len": 90},
        {"summary_compactor": {"max_goals": 4}},
    )
    assert policy["max_goals"] == 4
    assert policy["max_item_len"] == 90


def test_summary_compactor_merge_delta_path():
    prev = SummaryDTO(
        chat_id=uuid4(),
        goals=["g_old", "g_done"],
        done=["d_old"],
        entities={"incident": "INC-1"},
        open_questions=["q_old", "q_done"],
    )
    out = _LLMSummaryOutput(
        new_goals=["g_new"],
        completed_goals=["g_done"],
        new_entities={"repo": "ml-portal"},
        updated_entities={"incident": "INC-2"},
        resolved_questions=["q_done"],
        new_questions=["q_new"],
    )
    merged = _merge_summary(
        previous=prev,
        out=out,
        policy={
            "max_goals": 10,
            "max_done": 10,
            "max_entities": 10,
            "max_open_questions": 10,
            "max_item_len": 120,
        },
    )
    assert merged["goals"] == ["g_old", "g_new"]
    assert "g_done" in merged["done"]
    assert merged["entities"]["incident"] == "INC-2"
    assert merged["entities"]["repo"] == "ml-portal"
    assert merged["open_questions"] == ["q_old", "q_new"]
