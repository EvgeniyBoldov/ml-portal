from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.builtins.memory import MemoryMarkTool
from app.agents.context import ToolContext
from app.runtime.turn_state import RuntimeTurnState
from app.workers.tasks_memory import (
    MemoryFinalizePayload,
    ProjectMemoryCandidatePayload,
    SummaryPayload,
    _deserialize_turn_memory,
)


def _state() -> RuntimeTurnState:
    return RuntimeTurnState(run_id=uuid4(), user_id=uuid4(), tenant_id=uuid4())


@pytest.mark.asyncio
async def test_project_memory_marker_accepts_successful_same_run_evidence() -> None:
    state = _state()
    state.tool_ledger.register_call(
        operation="collection.document.search", call_id="search-1", arguments={},
        iteration=1, agent_slug="knowledge", phase_id="knowledge",
    )
    state.tool_ledger.register_result(call_id="search-1", success=True, data={"hits": ["rule"]})
    ctx = ToolContext(tenant_id=state.tenant_id, user_id=state.user_id)
    ctx.extra["runtime_turn_state"] = state
    ctx.extra["runtime_tool_ledger"] = state.tool_ledger

    result = await MemoryMarkTool().v1_0_0(ctx, {
        "project_key": "nemesis",
        "candidates": [{
            "subject": "network.ssh.access",
            "value": "SSH доступ разрешён только через management VRF.",
            "evidence_call_ids": ["search-1"],
            "aliases": ["NMS"],
        }],
    })

    assert result.success is True
    assert result.data == {"accepted": 1, "rejected": []}
    assert state.project_memory_candidates[0].project_key == "nemesis"


@pytest.mark.asyncio
async def test_project_memory_marker_rejects_missing_or_self_evidence() -> None:
    state = _state()
    ctx = ToolContext(tenant_id=state.tenant_id, user_id=state.user_id)
    ctx.extra["runtime_turn_state"] = state
    ctx.extra["runtime_tool_ledger"] = state.tool_ledger

    result = await MemoryMarkTool().v1_0_0(ctx, {
        "project_key": "nemesis",
        "candidates": [{
            "subject": "network.ssh.access",
            "value": "SSH доступ разрешён.",
            "evidence_call_ids": ["unknown"],
        }],
    })

    assert result.success is True
    assert result.data["accepted"] == 0
    assert result.data["rejected"][0]["reason"] == "evidence_must_reference_successful_current_run_tool"
    assert state.project_memory_candidates == []


def test_project_memory_candidates_survive_celery_payload() -> None:
    chat_id = uuid4()
    payload = MemoryFinalizePayload(
        chat_id=str(chat_id),
        turn_number=1,
        user_message="question",
        assistant_final="answer",
        summary=SummaryPayload(chat_id=str(chat_id)),
        project_memory_candidates=[ProjectMemoryCandidatePayload(
            project_key="nemesis",
            subject="network.ssh.access",
            value="SSH only through management VRF",
            evidence_call_ids=["call-1"],
            aliases=["NMS"],
        )],
    )

    memory = _deserialize_turn_memory(payload)

    assert memory.project_memory_candidates[0].project_key == "nemesis"
    assert memory.project_memory_candidates[0].evidence_call_ids == ["call-1"]
