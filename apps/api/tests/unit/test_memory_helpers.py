"""Unit tests for fact extraction and planner-memory preparation.

The LLM call itself is delegated to `StructuredLLMCall.invoke`. We
patch that method and focus on:

  * FactExtractor: post-validation rules (scope filtering, owner id
    sanity, clipping, cap) and fail-safe behaviour on exceptions.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import (
    StructuredCallError,
    StructuredCallResult,
)
from app.runtime.memory.fact_extractor import (
    AgentResultSnippet,
    FactEvidence,
    FactExtractor,
    _resolve_fact_policy,
    _LLMFactCandidate,
    _LLMFactOutput,
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
        _PreparationOutput(
            fact_indexes=[1], project_indexes=[0], glossary_indexes=[0],
            ambiguities=["Нема может означать два проекта"],
        )
    ))
    facts = [
        FactDTO(scope=FactScope.USER, subject="user.role", value="network engineer", source=FactSource.USER_UTTERANCE),
        FactDTO(scope=FactScope.TENANT, subject="tenant.standard", value="ITIL", source=FactSource.USER_UTTERANCE),
    ]
    result = await preparer.prepare(
        request_text="Нужна заявка для Немы", facts=facts,
        project_glossary=[{"id": uuid4(), "key": "nemesis", "name": "Немезида", "aliases": ["Нема"]}],
        glossary=[{"term": "срк", "description": "Система резервного копирования", "aliases": ["СРК"]}],
        user_id=uuid4(), tenant_id=uuid4(), chat_id=None, sandbox_overrides=None,
    )

    assert result.fallback is False
    assert result.items[0]["subject"] == "tenant.standard"
    assert result.items[1]["key"] == "nemesis"
    assert result.items[2] == {
        "type": "glossary",
        "scope": "global",
        "term": "срк",
        "description": "Система резервного копирования",
        "aliases": ["СРК"],
    }
    assert result.selected_glossary_count == 1
    assert result.ambiguities == ["Нема может означать два проекта"]
    call = preparer._structured.invoke.await_args
    assert call.kwargs["role"] is SystemLLMRoleType.MEMORY
    assert "system_prompt" not in call.kwargs


@pytest.mark.asyncio
async def test_memory_preparer_degrades_to_empty_context() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(side_effect=RuntimeError("offline"))

    result = await preparer.prepare(
        request_text="test", facts=[], project_glossary=[], glossary=[], user_id=None,
        tenant_id=None, chat_id=None, sandbox_overrides=None,
    )

    assert result.fallback is True
    assert result.items == []


@pytest.mark.asyncio
async def test_fact_extractor_rejects_project_fact_even_with_evidence(extractor) -> None:
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

    assert facts == []


@pytest.mark.asyncio
async def test_fact_extractor_keeps_tenant_glossary_candidate(extractor) -> None:
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(
        _LLMFactOutput(facts=[_LLMFactCandidate(
            scope="tenant", kind="glossary", subject="evpn",
            value="Ethernet VPN", aliases=["EVPN"], confidence=1.0,
        )])
    ))

    facts = await extractor.extract(
        user_message="В нашей сети EVPN означает Ethernet VPN",
        known_facts=[], user_id=uuid4(), tenant_id=uuid4(),
    )

    assert len(facts) == 1
    assert facts[0].kind == "glossary"
    assert facts[0].metadata["aliases"] == ["EVPN"]


@pytest.mark.asyncio
async def test_fact_extractor_promotes_grounded_glossary_to_global_candidate(extractor) -> None:
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(
        _LLMFactOutput(facts=[_LLMFactCandidate(
            scope="tenant", kind="glossary", subject="срк",
            value="Система резервного копирования", aliases=["СРК"],
            confidence=1.0, evidence_source_ids=["search-1"],
        )])
    ))

    facts = await extractor.extract(
        user_message="что такое срк",
        evidence=[FactEvidence(
            source_id="search-1", source_type="tool_result", source_ref="tool-call-1",
            support_ref="document-1", label="collection.document.search",
            text="СРК — система резервного копирования.",
        )],
        known_facts=[], user_id=uuid4(), tenant_id=uuid4(),
    )

    assert len(facts) == 1
    assert facts[0].metadata["glossary_scope"] == "global"


@pytest.mark.asyncio
async def test_fact_extractor_keeps_user_glossary_candidate(extractor) -> None:
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(
        _LLMFactOutput(facts=[_LLMFactCandidate(
            scope="user", kind="glossary", subject="my acronym",
            value="personal shorthand", aliases=["MA"], confidence=1.0,
        )])
    ))

    facts = await extractor.extract(
        user_message="Для меня MA означает personal shorthand",
        known_facts=[], user_id=uuid4(), tenant_id=uuid4(),
    )

    assert len(facts) == 1
    assert facts[0].scope == FactScope.USER
    assert facts[0].kind == "glossary"
