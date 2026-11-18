from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.services.runtime_progress_streamer import RuntimeProgressStreamer


def _description(mode: str, iteration_type: str) -> str:
    event = RuntimeEvent.planner_iteration_start(
        iteration_id="iteration-1",
        orchestrator_id="orchestrator-1",
        iteration=1,
        iteration_type=iteration_type,
        mode=mode,
    )
    progress = RuntimeProgressStreamer().project(
        event,
        run_id="run-1",
        phase=OrchestrationPhase.PLANNER,
    )
    assert progress is not None
    return progress["description"]


def test_planner_iteration_progress_uses_iteration_mode() -> None:
    assert _description("initial", "decision") == "Формирую план выполнения"
    assert _description("replan", "replan") == "Перепланирую выполнение"
    assert _description("checkpoint", "checkpoint") == "Определяю следующие шаги"
    assert _description("resume", "execution") == "Выполняю план"


def test_projection_keeps_shared_tail_envelope_and_adds_normalized_chat_stage() -> None:
    event = RuntimeEvent(RuntimeEventType.TASK_STARTED, {"intent": "private task detail"})
    progress = RuntimeProgressStreamer().project(
        event, run_id="run-1", phase=OrchestrationPhase.PLANNER,
    )
    assert progress is not None
    assert progress["type"] == "runtime_progress"  # sandbox wire compatibility
    assert progress["chat_stage"] == "executing"
    assert progress["action"] == "task_started"
    assert "private task detail" not in progress["description"]


def test_synthesis_progress_has_descriptions_stage_and_terminal_outcome() -> None:
    streamer = RuntimeProgressStreamer()
    started = streamer.project(
        RuntimeEvent.synthesis_start(synthesis_id="synth-1", run_id="run-1"),
        run_id="run-1", phase=OrchestrationPhase.SYNTHESIS,
    )
    ended = streamer.project(
        RuntimeEvent.synthesis_end(
            synthesis_id="synth-1", run_id="run-1", status="failed", error_code="synthesis_failed",
        ),
        run_id="run-1", phase=OrchestrationPhase.SYNTHESIS,
    )

    assert started is not None
    assert started["chat_stage"] == "synthesizing"
    assert started["description"]
    assert ended is not None
    assert ended["chat_stage"] == "synthesizing"
    assert ended["status"] == ended["outcome"] == "failed"
    assert ended["description"] == "Не удалось собрать итоговый ответ"


def test_synthesis_end_without_status_does_not_claim_success() -> None:
    event = RuntimeEvent.synthesis_end(synthesis_id="synth-1", run_id="run-1", status="")
    progress = RuntimeProgressStreamer().project(
        event, run_id="run-1", phase=OrchestrationPhase.SYNTHESIS,
    )

    assert progress is not None
    assert progress["outcome"] is None
    assert "собран" not in progress["description"].lower()
