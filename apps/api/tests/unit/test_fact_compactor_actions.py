from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import FactScope, FactSource
from app.runtime.llm.structured import StructuredCallResult
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.fact_compactor import FactCompactor, _CompactedFact, _CompactionOutput


def _result(value):
    return StructuredCallResult(value=value, trace_id=None, raw_response="", duration_ms=1, model="test", request_messages=[], request_params={})


@pytest.mark.asyncio
async def test_compactor_preserves_llm_selected_supersede_targets() -> None:
    target = FactDTO(
        scope=FactScope.TENANT, subject="network.access", value="Legacy rule",
        source=FactSource.TOOL_RESULT,
    )
    candidate = FactDTO(
        scope=FactScope.TENANT, subject="network.access", value="New compact rule",
        source=FactSource.TOOL_RESULT, metadata={"evidence": [{"source_type": "tool_result", "source_ref": "call-1"}]},
    )
    compactor = FactCompactor(session=AsyncMock(), llm_client=AsyncMock())
    compactor._structured.invoke = AsyncMock(return_value=_result(_CompactionOutput(facts=[
        _CompactedFact(
            scope="tenant", subject="network.access", value="New compact rule",
            action="supersede", source_candidate_indexes=[0], target_current_indexes=[0],
        )
    ])))

    result = await compactor.compact(
        candidates=[candidate], current_facts=[target], user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4(),
    )

    assert result[0].metadata["compaction_action"] == "supersede"
    assert result[0].metadata["compaction_target_ids"] == [str(target.id)]


@pytest.mark.asyncio
async def test_compactor_keeps_evidenced_candidates_omitted_by_partial_llm_output() -> None:
    first = FactDTO(
        scope=FactScope.USER,
        subject="role",
        value="network engineer",
        source=FactSource.USER_UTTERANCE,
        metadata={"evidence": [{"source_type": "user_message", "source_ref": "turn-1"}]},
    )
    omitted = FactDTO(
        scope=FactScope.USER,
        subject="preferred language",
        value="Russian",
        source=FactSource.USER_UTTERANCE,
        metadata={"evidence": [{"source_type": "user_message", "source_ref": "turn-1"}]},
    )
    compactor = FactCompactor(session=AsyncMock(), llm_client=AsyncMock())
    compactor._structured.invoke = AsyncMock(return_value=_result(_CompactionOutput(facts=[
        _CompactedFact(
            scope="user",
            subject="role",
            value="network engineer",
            action="add",
            source_candidate_indexes=[0],
        )
    ])))

    result = await compactor.compact(
        candidates=[first, omitted],
        current_facts=[],
        user_id=uuid4(),
        tenant_id=uuid4(),
        chat_id=uuid4(),
    )

    assert {(item.subject, item.value) for item in result} == {
        ("role", "network engineer"),
        ("preferred language", "Russian"),
    }


@pytest.mark.asyncio
async def test_compactor_cannot_replace_an_evidenced_value_with_an_ungrounded_one() -> None:
    candidate = FactDTO(
        scope=FactScope.USER,
        subject="role",
        value="network engineer",
        source=FactSource.USER_UTTERANCE,
        metadata={"evidence": [{"source_type": "user_message", "source_ref": "turn-1", "text": "I am a network engineer."}]},
    )
    compactor = FactCompactor(session=AsyncMock(), llm_client=AsyncMock())
    compactor._structured.invoke = AsyncMock(return_value=_result(_CompactionOutput(facts=[
        _CompactedFact(
            scope="user", subject="security.clearance", value="top secret",
            action="rewrite", source_candidate_indexes=[0],
        )
    ])))

    result = await compactor.compact(
        candidates=[candidate], current_facts=[], user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4(),
    )

    assert result[0].subject == "role"
    assert result[0].value == "network engineer"


@pytest.mark.asyncio
async def test_compactor_forwards_its_execution_id_to_structured_llm() -> None:
    candidate = FactDTO(
        scope=FactScope.USER,
        subject="role",
        value="network engineer",
        source=FactSource.USER_UTTERANCE,
    )
    compactor = FactCompactor(session=AsyncMock(), llm_client=AsyncMock())
    compactor._structured.invoke = AsyncMock(return_value=_result(_CompactionOutput()))

    await compactor.compact(
        candidates=[candidate],
        current_facts=[],
        user_id=uuid4(),
        tenant_id=uuid4(),
        chat_id=uuid4(),
        event_sink=AsyncMock(),
        agent_execution_id="fact-compactor-execution",
    )

    assert compactor._structured.invoke.await_args.kwargs["agent_execution_id"] == "fact-compactor-execution"
