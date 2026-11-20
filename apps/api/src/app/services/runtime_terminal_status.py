from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple

from app.runtime.events import RuntimeEvent, RuntimeEventType


class RunTerminalStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    STOPPED = "stopped"


def normalize_run_terminal_status(reason: Optional[str]) -> RunTerminalStatus:
    value = str(reason or "").strip()
    if value == RunTerminalStatus.WAITING_INPUT.value:
        return RunTerminalStatus.WAITING_INPUT
    if value == RunTerminalStatus.WAITING_CONFIRMATION.value:
        return RunTerminalStatus.WAITING_CONFIRMATION
    if value == RunTerminalStatus.FAILED.value:
        return RunTerminalStatus.FAILED
    if value == RunTerminalStatus.COMPLETED.value:
        return RunTerminalStatus.COMPLETED
    return RunTerminalStatus.STOPPED


def planner_terminal_from_event(event: RuntimeEvent) -> Optional[Tuple[RunTerminalStatus, Optional[str]]]:
    if event.type == RuntimeEventType.FINAL:
        stop_reason = str(event.data.get("stop_reason") or "").strip()
        normalized = normalize_run_terminal_status(stop_reason)
        if normalized not in (RunTerminalStatus.STOPPED, RunTerminalStatus.COMPLETED):
            return normalized, None
        return RunTerminalStatus.COMPLETED, None
    if event.type == RuntimeEventType.ERROR:
        return RunTerminalStatus.FAILED, str(event.data.get("error") or "runtime_error")
    if event.type == RuntimeEventType.STOP:
        status = normalize_run_terminal_status(str(event.data.get("reason") or ""))
        message = str(event.data.get("message") or event.data.get("question") or "")
        return status, message
    return None

