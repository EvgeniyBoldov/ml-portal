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
        scope=FactScope.PROJECT, subject="network.access", value="Legacy rule",
        source=FactSource.TOOL_RESULT, metadata={"project_key": "nemesis"},
    )
    candidate = FactDTO(
        scope=FactScope.PROJECT, subject="network.access", value="New compact rule",
        source=FactSource.TOOL_RESULT, metadata={"project_key": "nemesis", "evidence": [{"source_type": "tool_result", "source_ref": "call-1"}]},
    )
    compactor = FactCompactor(session=AsyncMock(), llm_client=AsyncMock())
    compactor._structured.invoke = AsyncMock(return_value=_result(_CompactionOutput(facts=[
        _CompactedFact(
            scope="project", subject="network.access", value="New compact rule",
            action="supersede", source_candidate_indexes=[0], target_current_indexes=[0],
        )
    ])))

    result = await compactor.compact(
        candidates=[candidate], current_facts=[target], user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4(),
    )

    assert result[0].metadata["compaction_action"] == "supersede"
    assert result[0].metadata["compaction_target_ids"] == [str(target.id)]
