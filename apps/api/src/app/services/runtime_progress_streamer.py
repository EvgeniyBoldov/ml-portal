"""Safe user-facing projection of canonical runtime events.

The streamer is a transport adapter. Runtime components never call it directly:
they emit one semantic event to ``RuntimeEventLogger``.
"""
from __future__ import annotations

from typing import Any, Optional

from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType


class RuntimeProgressStreamer:
    _MAX_DESCRIPTION_LENGTH = 240
    _MECHANICAL = {
        RuntimeEventType.RUN_START: "Запускаю выполнение",
        RuntimeEventType.ORCHESTRATOR_START: "Запускаю планирование",
        RuntimeEventType.PLAN_CREATED: "План готов",
        RuntimeEventType.PLAN_ITERATION_APPLIED: "Формирую следующую итерацию",
        RuntimeEventType.TASK_STARTED: "Начинаю задачу",
        RuntimeEventType.AGENT_START: "Запускаю агента",
        RuntimeEventType.LLM_REQUEST: "Анализирую задачу",
        RuntimeEventType.LLM_RESPONSE: "Получен ответ модели",
        RuntimeEventType.TOOL_CALL: "Выполняю инструмент",
        RuntimeEventType.TOOL_RESULT: "Получен результат инструмента",
        RuntimeEventType.PROTOCOL_RETRY: "Ожидаю повтор вызова",
        RuntimeEventType.PREFLIGHT_STARTED: "Проверяю доступные возможности",
        RuntimeEventType.EXTRACTION_STARTED: "Извлекаю содержимое файла",
        RuntimeEventType.CONFIRMATION_REQUIRED: "Ожидаю подтверждение",
        RuntimeEventType.WAITING_INPUT: "Ожидаю уточнение",
        RuntimeEventType.TASK_COMPLETED: "Задача завершена",
        RuntimeEventType.PLAN_COMPLETED: "Выполнение завершено",
        RuntimeEventType.AGENT_END: "Агент завершил работу",
        RuntimeEventType.ERROR: "Во время выполнения возникла ошибка",
    }

    _STAGE_BY_KIND = {
        RuntimeEventType.RUN_START: "preparing",
        RuntimeEventType.ORCHESTRATOR_START: "planning",
        RuntimeEventType.PLANNER_ITERATION_START: "planning",
        RuntimeEventType.PLANNER_ITERATION_END: "planning",
        RuntimeEventType.PLAN_CREATED: "planning",
        RuntimeEventType.PLAN_ITERATION_APPLIED: "planning",
        RuntimeEventType.TASK_PLANNED: "planning",
        RuntimeEventType.TASK_STARTED: "executing",
        RuntimeEventType.AGENT_START: "executing",
        RuntimeEventType.AGENT_END: "executing",
        RuntimeEventType.TOOL_CALL: "executing",
        RuntimeEventType.TOOL_RESULT: "executing",
        RuntimeEventType.EXTRACTION_STARTED: "executing",
        RuntimeEventType.EXTRACTION_COMPLETED: "executing",
        RuntimeEventType.SYNTHESIS_START: "synthesizing",
        RuntimeEventType.SYNTHESIS_END: "synthesizing",
        RuntimeEventType.FINAL_ANSWER_MARKER: "finalizing",
    }

    def project(self, event: RuntimeEvent, *, run_id: str, phase: OrchestrationPhase) -> Optional[dict[str, Any]]:
        description = self._description(event)
        if description is None:
            return None
        data = event.data
        outcome = data.get("status")
        if outcome not in {"completed", "failed", "cancelled", "error"}:
            outcome = None
        return {
            # Keep the shared runtime-tail envelope stable for sandbox readers.
            # Chat consumes the additional normalized stage/activity fields.
            "type": "runtime_progress",
            "run_id": run_id,
            "phase": phase.value,
            "kind": event.type.value,
            "description": description,
            "status": data.get("status"),
            "chat_stage": self._stage(event, phase),
            "action": event.type.value,
            "outcome": outcome,
        }

    def _stage(self, event: RuntimeEvent, phase: OrchestrationPhase) -> str:
        explicit = self._STAGE_BY_KIND.get(event.type)
        if explicit:
            return explicit
        return {
            OrchestrationPhase.PREFLIGHT: "planning",
            OrchestrationPhase.PLANNER: "planning",
            OrchestrationPhase.AGENT: "executing",
            OrchestrationPhase.SYNTHESIS: "synthesizing",
            OrchestrationPhase.PIPELINE: "executing",
        }[phase]

    def _description(self, event: RuntimeEvent) -> Optional[str]:
        if event.type is RuntimeEventType.PLANNER_ITERATION_START:
            mode = str(event.data.get("mode") or "").lower()
            iteration_type = str(event.data.get("iteration_type") or "").lower()
            if mode == "initial":
                return "Формирую план выполнения"
            if mode == "replan" or iteration_type == "replan":
                return "Перепланирую выполнение"
            if mode == "checkpoint" or iteration_type == "checkpoint":
                return "Определяю следующие шаги"
            if mode == "resume" or iteration_type == "execution":
                return "Выполняю план"
            return "Планирую выполнение"
        mechanical = self._MECHANICAL.get(event.type)
        if mechanical is None:
            return None
        if event.type is RuntimeEventType.PROTOCOL_RETRY:
            delay = event.data.get("retry_delay_ms")
            suffix = f", повтор через {delay / 1000:g} с" if isinstance(delay, int) and delay > 0 else ""
            return self._bounded(f"{mechanical}{suffix}")
        return mechanical

    def _bounded(self, value: str) -> Optional[str]:
        text = " ".join(value.split())
        if not text:
            return None
        if len(text) <= self._MAX_DESCRIPTION_LENGTH:
            return text
        return f"{text[: self._MAX_DESCRIPTION_LENGTH - 1].rstrip()}…"
