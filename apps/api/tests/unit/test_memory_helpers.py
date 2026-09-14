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
from pydantic import ValidationError

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
from app.runtime.memory.preparer import (
    MemoryPreparer, _PreparationOutput, _conservative_intent,
    _requires_current_observation,
)
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


def test_current_state_request_requires_runtime_observation() -> None:
    assert _requires_current_observation("Какой сейчас статус коммутатора?") is True
    assert _requires_current_observation("Опиши процедуру изменения VLAN") is False


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
async def test_fact_extractor_sends_primary_text_only_once(extractor):
    extractor._structured.invoke = AsyncMock(return_value=_llm_result(_LLMFactOutput()))
    source_text = "Термин\nОпределение"

    await extractor.extract(
        user_message=source_text,
        evidence=[FactEvidence(
            source_id="user_message", source_type="user_message",
            source_ref="turn-1", text=source_text,
        )],
        preflight_candidates=[{
            "scope": "tenant", "kind": "glossary",
            "subject": "Термин", "value": "Определение",
        }],
        known_facts=[], tenant_id=uuid4(),
    )

    payload = extractor._structured.invoke.await_args.kwargs["payload"]
    assert "user_message" not in payload
    assert payload["evidence"][0]["text"] == source_text
    assert payload["preflight_candidates"][0]["subject"] == "Термин"


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


def test_fact_extractor_records_safe_validation_decisions() -> None:
    result = FactExtractor._to_dtos_with_decisions(
        _LLMFactOutput(facts=[
            _LLMFactCandidate(scope="global", subject="x", value="y", confidence=1.0),
            _LLMFactCandidate(scope="user", subject="user.name", value="Anna", confidence=1.0),
        ]),
        user_message="My name is Anna", evidence=[FactEvidence(
            source_id="user_message", source_type="user_message", source_ref="turn-1", text="My name is Anna",
        )], user_id=uuid4(), tenant_id=None, chat_id=None,
    )

    assert [item.reason_code for item in result.decisions] == ["unknown_scope", "evidence_validated"]
    assert result.decisions[1].compact_view()["candidate_ids"] == ["extractor:2"]


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
    assert len(facts) == 12


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
async def test_memory_preparer_fallback_preserves_current_state_tool_requirement() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(side_effect=RuntimeError("offline"))
    result = await preparer.prepare(
        request_text="Какой сейчас статус коммутатора?", facts=[], project_glossary=[], glossary=[],
        user_id=None, tenant_id=None, chat_id=None, sandbox_overrides=None,
    )
    assert result.fallback is True
    assert result.tool_required is True


def test_action_request_cannot_be_downgraded_by_memory_selector() -> None:
    assert _conservative_intent("Измени VLAN в production", "informational") == "action"


@pytest.mark.asyncio
async def test_memory_preparer_adds_selected_project_knowledge() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(return_value=_llm_result(
        _PreparationOutput(memory_indexes=[0])
    ))

    result = await preparer.prepare(
        request_text="Как поменять VLAN в Сфере?",
        facts=[],
        project_glossary=[{"id": "p1", "key": "sphere", "name": "Сфера", "aliases": []}],
        project_facts=[
            {
                "project_id": "p1",
                "project_key": "sphere",
                "kind": "procedure",
                "subject": "network.change_vlan",
                "value": "Перед изменением VLAN сохранить конфигурацию.",
                "confidence": 0.95,
                "source_ref": "document-1#section-3",
            },
        ],
        glossary=[], user_id=None, tenant_id=None, chat_id=None, sandbox_overrides=None,
    )

    assert result.selected_project_fact_count == 1
    assert result.items[-1]["type"] == "project_knowledge"
    assert result.items[-1]["kind"] == "procedure"
    assert result.items[-1]["project_key"] == "sphere"
    # A how-to request is informational; executing the change is a separate
    # intent and must not force a live runtime observation.
    assert result.needs_source_check is False
    assert result.intent == "informational"


@pytest.mark.asyncio
async def test_memory_preparer_keeps_model_selected_semantic_hit_without_lexical_overlap() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(return_value=_llm_result(
        _PreparationOutput(memory_indexes=[0], intent="informational")
    ))
    result = await preparer.prepare(
        request_text="Какой порядок для сегментации сети?", facts=[], project_glossary=[], glossary=[],
        project_facts=[{
            "project_id": None, "kind": "procedure", "subject": "switch.vlan_change",
            "value": "Перед изменением VLAN сохранить конфигурацию.", "confidence": 0.95,
            "state": "active",
        }],
        user_id=None, tenant_id=None, chat_id=None, sandbox_overrides=None,
    )
    assert result.selected_project_fact_count == 1
    assert result.items[0]["subject"] == "switch.vlan_change"


@pytest.mark.asyncio
async def test_memory_preparer_keeps_active_procedure_when_its_source_is_old_but_not_stale() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(return_value=_llm_result(
        _PreparationOutput(memory_indexes=[0], intent="informational")
    ))

    result = await preparer.prepare(
        request_text="Что известно о VLAN в Сфере?",
        facts=[],
        project_glossary=[{"id": "p1", "key": "sphere", "name": "Сфера", "aliases": []}],
        project_facts=[{
            "project_id": "p1", "project_key": "sphere", "kind": "procedure",
            "subject": "network.change_vlan", "value": "Сохранить конфигурацию.",
            "confidence": 0.95, "observed_at": "2020-01-01T00:00:00+00:00",
        }],
        glossary=[], user_id=None, tenant_id=None, chat_id=None, sandbox_overrides=None,
    )

    assert any(item.get("type") == "project_knowledge" for item in result.items)
    assert "semantic_memory_stale" not in result.source_check_reasons


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
async def test_memory_preparer_drops_unrelated_user_pii_selected_by_model() -> None:
    preparer = MemoryPreparer(session=AsyncMock(), llm_client=AsyncMock())
    preparer._structured.invoke = AsyncMock(return_value=_llm_result(
        _PreparationOutput(fact_indexes=[0, 1, 2])
    ))
    facts = [
        FactDTO(scope=FactScope.USER, subject="имя", value="Софья", source=FactSource.USER_UTTERANCE),
        FactDTO(scope=FactScope.USER, subject="возраст", value="45", source=FactSource.USER_UTTERANCE),
        FactDTO(scope=FactScope.USER, subject="хобби", value="теннис", source=FactSource.USER_UTTERANCE),
    ]

    result = await preparer.prepare(
        request_text="Подробно опиши NIMS-3451", facts=facts,
        project_glossary=[], glossary=[], user_id=uuid4(), tenant_id=uuid4(),
        chat_id=None, sandbox_overrides=None,
    )

    assert result.items == []
    assert result.selected_fact_count == 0


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


def test_fact_extractor_kind_is_a_strict_storage_route() -> None:
    """Terms must be explicitly routed to glossary, never guessed from labels."""
    with pytest.raises(ValidationError):
        _LLMFactCandidate(
            scope="tenant", kind="definition", subject="аварийная ситуация",
            value="ситуация с вероятностью возникновения аварии", confidence=1.0,
        )


@pytest.mark.asyncio
async def test_fact_extractor_keeps_grounded_glossary_in_tenant_candidate(extractor) -> None:
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
    assert facts[0].metadata["glossary_scope"] is None


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
