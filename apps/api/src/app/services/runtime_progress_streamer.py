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
        RuntimeEventType.PLANNER_ITERATION_START: "Уточняю план выполнения",
        RuntimeEventType.PLAN_CREATED: "План готов",
        RuntimeEventType.PLAN_PATCH_APPLIED: "Обновляю план",
        RuntimeEventType.TASK_STARTED: "Начинаю задачу",
        RuntimeEventType.AGENT_START: "Запускаю агента",
        RuntimeEventType.LLM_REQUEST: "Анализирую задачу",
        RuntimeEventType.TOOL_CALL: "Выполняю инструмент",
        RuntimeEventType.PREFLIGHT_STARTED: "Проверяю доступные возможности",
        RuntimeEventType.EXTRACTION_STARTED: "Извлекаю содержимое файла",
        RuntimeEventType.CONFIRMATION_REQUIRED: "Ожидаю подтверждение",
        RuntimeEventType.WAITING_INPUT: "Ожидаю уточнение",
        RuntimeEventType.TASK_COMPLETED: "Задача завершена",
        RuntimeEventType.PLAN_COMPLETED: "Выполнение завершено",
        RuntimeEventType.AGENT_END: "Агент завершил работу",
        RuntimeEventType.ERROR: "Во время выполнения возникла ошибка",
    }

    def project(self, event: RuntimeEvent, *, run_id: str, phase: OrchestrationPhase) -> Optional[dict[str, Any]]:
        description = self._description(event)
        if description is None:
            return None
        data = event.data
        return {
            "type": "runtime_progress",
            "run_id": run_id,
            "phase": phase.value,
            "kind": event.type.value,
            "description": description,
            "entity_type": data.get("entity_type"),
            "entity_id": data.get("entity_id"),
            "parent_entity_type": data.get("parent_entity_type"),
            "parent_entity_id": data.get("parent_entity_id"),
            "status": data.get("status"),
        }

    def _description(self, event: RuntimeEvent) -> Optional[str]:
        candidate = event.data.get("progress_description")
        if not isinstance(candidate, str) and event.type is RuntimeEventType.INTENT:
            candidate = event.data.get("description")
        if isinstance(candidate, str):
            return self._bounded(candidate)
        mechanical = self._MECHANICAL.get(event.type)
        if mechanical is None:
            return None
        if event.type is RuntimeEventType.AGENT_START and event.data.get("agent_slug"):
            return f"{mechanical}: {event.data['agent_slug']}"
        if event.type is RuntimeEventType.TOOL_CALL and event.data.get("tool"):
            return f"{mechanical}: {event.data['tool']}"
        if event.type is RuntimeEventType.TASK_STARTED and event.data.get("intent"):
            return f"{mechanical}: {event.data['intent']}"
        if event.type is RuntimeEventType.AGENT_END and isinstance(event.data.get("summary"), str):
            summary = self._bounded(event.data["summary"])
            if summary:
                slug = str(event.data.get("agent_slug") or "агент")
                return self._bounded(f"{slug}: {summary}")
        return mechanical

    def _bounded(self, value: str) -> Optional[str]:
        text = " ".join(value.split())
        if not text:
            return None
        if len(text) <= self._MAX_DESCRIPTION_LENGTH:
            return text
        return f"{text[: self._MAX_DESCRIPTION_LENGTH - 1].rstrip()}…"
