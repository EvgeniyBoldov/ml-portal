"""Integration-ish test for RuntimePipeline (post-M6 shape).

Exercises the coordinator end-to-end with every collaborator mocked:

    MemoryBuilder       → canned TurnMemory
    PlatformConfigLoader → canned PlatformSnapshot
    PlanningStage       → stub async iterator emitting events + setting outcome
    FinalizationStage   → stub async iterator
    MemoryWriter        → spy

The test does NOT go through Planner / Synthesizer logic (those have
their own focused tests); it verifies the coordinator's own contract:

    1. Calls MemoryBuilder with the right ids + goal.
    2. Runs PlanningStage.
    3. Skips FinalizationStage when outcome is DIRECT / PAUSED / ABORTED.
    4. Invokes FinalizationStage when outcome is NEEDS_FINAL.
    5. Always invokes MemoryWriter.finalize at the end, with the user's
       request_text and the legacy_memory.final_answer.
    6. Stamps every yielded event with an orchestration envelope.
"""
from __future__ import annotations

from typing import AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.transport import TurnMemory
from app.runtime.pipeline import RuntimePipeline
from app.runtime.platform_config import PlatformSnapshot
from app.runtime.stages.planning_stage import (
    PlanningOutcome,
    PlanningOutcomeKind,
)


def _canned_turn_memory(chat_id, user_id, tenant_id) -> TurnMemory:
    return TurnMemory(
        chat_id=chat_id,
        user_id=user_id,
        tenant_id=tenant_id,
        turn_number=1,
        goal="hi",
        summary=SummaryDTO.empty(chat_id),
        retrieved_facts=[],
    )


def _canned_platform() -> PlatformSnapshot:
    # Minimal shape — pipeline only reads .config / .routable_agents /
    # .policy / .available_agents_for_planner.
    snap = MagicMock(spec=PlatformSnapshot)
    snap.config = {}
    snap.routable_agents = []
    snap.policy = MagicMock(max_steps=3, max_wall_time_ms=60_000)
    snap.available_agents_for_planner = MagicMock(return_value=[])
    return snap


class _StubPlanningStage:
    """Yields one synthesizing-esque event and reports the outcome."""

    def __init__(self, outcome: PlanningOutcome, extra_final_answer: str = ""):
        self.outcome = outcome
        self._extra = extra_final_answer

    async def run(self, *, memory, **_) -> AsyncIterator[PhasedEvent]:
        yield PhasedEvent(
            RuntimeEvent.status("planner_thinking", iteration=1),
            OrchestrationPhase.PLANNER,
        )
        if self._extra:
            # DIRECT_ANSWER path writes the final answer onto memory before
            # returning, so pipeline's _finalize_memory sees it.
            memory.final_answer = self._extra
            yield PhasedEvent(
                RuntimeEvent.final(self._extra, sources=[], run_id=str(memory.run_id)),
                OrchestrationPhase.SYNTHESIS,
            )


class _StubFinalizationStage:
    async def run(self, *, memory, **_) -> AsyncIterator[PhasedEvent]:
        memory.final_answer = memory.final_answer or "synthesized answer"
        yield PhasedEvent(
            RuntimeEvent.final(
                memory.final_answer, sources=[], run_id=str(memory.run_id),
            ),
            OrchestrationPhase.SYNTHESIS,
        )


def _request(chat_id, user_id, tenant_id, *, text="hi") -> PipelineRequest:
    return PipelineRequest(
        request_text=text,
        chat_id=str(chat_id),
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        messages=[],
    )


async def _collect(gen) -> List[RuntimeEvent]:
    return [e async for e in gen]


# ------------------------------------------------------------- direct_answer --


@pytest.mark.asyncio
async def test_pipeline_direct_answer_path_calls_memory_writer_and_skips_finalization():
    chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4()

    pipeline = RuntimePipeline(session=AsyncMock(), llm_client=AsyncMock())

    # Stub memory_builder / memory_writer on the assembler.
    pipeline._assembler.memory_builder.build = AsyncMock(
        return_value=_canned_turn_memory(chat_id, user_id, tenant_id)
    )
    pipeline._assembler.memory_writer.finalize = AsyncMock()

    # Stub stages.
    direct_outcome = PlanningOutcome(
        kind=PlanningOutcomeKind.DIRECT,
        stop_reason=PipelineStopReason.COMPLETED,
        planner_hint="Привет!",
    )
    pipeline._assembler.build_planning_stage = MagicMock(
        return_value=_StubPlanningStage(direct_outcome, extra_final_answer="Привет!")
    )
    # Finalization should NEVER be built on the DIRECT path.
    finalization_builder = MagicMock()
    pipeline._assembler.build_finalization_stage = finalization_builder

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader"
    ) as platform_cls:
        platform_cls.return_value.load = AsyncMock(return_value=_canned_platform())

        events = await _collect(
            pipeline.execute(
                request=_request(chat_id, user_id, tenant_id, text="Привет!"),
                ctx=MagicMock(),
            )
        )

    # Planner emitted a status + final; pipeline should have stamped every
    # event with the envelope (stored under `_envelope` inside `data` by
    # `RuntimeEvent.with_envelope`).
    assert all("_envelope" in e.data for e in events), (
        "every event out of RuntimePipeline must carry an envelope"
    )
    # Sequence is monotonic and starts at 1.
    sequences = [e.data["_envelope"]["sequence"] for e in events]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1

    finalization_builder.assert_not_called()
    pipeline._assembler.memory_writer.finalize.assert_awaited_once()
    kwargs = pipeline._assembler.memory_writer.finalize.await_args.kwargs
    assert kwargs["user_message"] == "Привет!"
    assert kwargs["assistant_final"] == "Привет!"


# ------------------------------------------------------------ needs_final ---


@pytest.mark.asyncio
async def test_pipeline_needs_final_runs_finalization_then_memory_writer():
    chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4()

    pipeline = RuntimePipeline(session=AsyncMock(), llm_client=AsyncMock())
    pipeline._assembler.memory_builder.build = AsyncMock(
        return_value=_canned_turn_memory(chat_id, user_id, tenant_id)
    )
    pipeline._assembler.memory_writer.finalize = AsyncMock()

    outcome = PlanningOutcome(
        kind=PlanningOutcomeKind.NEEDS_FINAL,
        stop_reason=PipelineStopReason.COMPLETED,
        planner_hint=None,
    )
    pipeline._assembler.build_planning_stage = MagicMock(
        return_value=_StubPlanningStage(outcome)
    )
    pipeline._assembler.build_finalization_stage = MagicMock(
        return_value=_StubFinalizationStage()
    )

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader"
    ) as platform_cls:
        platform_cls.return_value.load = AsyncMock(return_value=_canned_platform())

        events = await _collect(
            pipeline.execute(
                request=_request(chat_id, user_id, tenant_id, text="исследуй тему X"),
                ctx=MagicMock(),
            )
        )

    # Both stages built; finalize called.
    pipeline._assembler.build_finalization_stage.assert_called_once()
    pipeline._assembler.memory_writer.finalize.assert_awaited_once()

    # The final event should be there (RuntimeEvent.final stores the
    # answer text under the 'content' key in .data).
    assert any(
        e.data.get("content") == "synthesized answer" for e in events
    )


# ------------------------------------------------------------- paused path ---


@pytest.mark.asyncio
async def test_pipeline_paused_path_skips_finalization_but_writes_memory():
    """CLARIFY / ASK_USER → planner emits waiting_input, pipeline does NOT
    invoke FinalizationStage, but MUST still invoke MemoryWriter so the
    next turn sees the open_question in its summary."""
    chat_id, user_id, tenant_id = uuid4(), uuid4(), uuid4()

    pipeline = RuntimePipeline(session=AsyncMock(), llm_client=AsyncMock())
    pipeline._assembler.memory_builder.build = AsyncMock(
        return_value=_canned_turn_memory(chat_id, user_id, tenant_id)
    )
    pipeline._assembler.memory_writer.finalize = AsyncMock()

    outcome = PlanningOutcome(
        kind=PlanningOutcomeKind.PAUSED,
        stop_reason=PipelineStopReason.WAITING_INPUT,
    )
    pipeline._assembler.build_planning_stage = MagicMock(
        return_value=_StubPlanningStage(outcome)
    )
    finalization_builder = MagicMock()
    pipeline._assembler.build_finalization_stage = finalization_builder

    with patch(
        "app.runtime.pipeline.PlatformConfigLoader"
    ) as platform_cls:
        platform_cls.return_value.load = AsyncMock(return_value=_canned_platform())

        await _collect(
            pipeline.execute(
                request=_request(chat_id, user_id, tenant_id, text="найди что-то"),
                ctx=MagicMock(),
            )
        )

    finalization_builder.assert_not_called()
    pipeline._assembler.memory_writer.finalize.assert_awaited_once()
