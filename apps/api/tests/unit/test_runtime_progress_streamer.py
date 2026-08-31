from app.runtime.events import OrchestrationPhase, RuntimeEvent
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
