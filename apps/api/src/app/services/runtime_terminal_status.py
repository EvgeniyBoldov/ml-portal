from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.runtime.events import RuntimeEvent, RuntimeEventType


class RunTerminalStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    STOPPED = "stopped"


class ContinuationTerminalStatus(str, Enum):
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


class ContinuationApiStatus(str, Enum):
    RESUMED_COMPLETED = "resumed_completed"
    RESUMED_WITH_ERROR = "resumed_with_error"
    RESUMED_PAUSED_AGAIN = "resumed_paused_again"


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


def normalize_run_status_for_storage(status: Optional[str]) -> str:
    """
    Normalize AgentRun.status values persisted in DB.

    Keeps lifecycle statuses used outside finish flow (running/resumed/cancelled),
    and normalizes runtime terminal statuses to canonical values.
    """
    value = str(status or "").strip()
    passthrough = {"running", "resumed", "cancelled"}
    if value in passthrough:
        return value
    return normalize_run_terminal_status(value).value


def planner_terminal_from_event(event: RuntimeEvent) -> Optional[Tuple[RunTerminalStatus, Optional[str]]]:
    if event.type == RuntimeEventType.FINAL:
        return RunTerminalStatus.COMPLETED, None
    if event.type == RuntimeEventType.ERROR:
        return RunTerminalStatus.FAILED, str(event.data.get("error") or "runtime_error")
    if event.type == RuntimeEventType.STOP:
        status = normalize_run_terminal_status(str(event.data.get("reason") or ""))
        message = str(event.data.get("message") or event.data.get("question") or "")
        return status, message
    return None


def continuation_terminal_from_event(event: Dict[str, Any]) -> Optional[Tuple[ContinuationTerminalStatus, Optional[str]]]:
    event_type = str(event.get("type") or "")
    if event_type == "error":
        return ContinuationTerminalStatus.ERROR, str(event.get("error") or "Unknown continuation error")
    if event_type == "run_paused":
        return ContinuationTerminalStatus.PAUSED, str(event.get("reason") or "")
    if event_type == "final":
        return ContinuationTerminalStatus.COMPLETED, None
    return None


def continuation_api_status_from_terminal(status: ContinuationTerminalStatus) -> ContinuationApiStatus:
    if status == ContinuationTerminalStatus.ERROR:
        return ContinuationApiStatus.RESUMED_WITH_ERROR
    if status == ContinuationTerminalStatus.PAUSED:
        return ContinuationApiStatus.RESUMED_PAUSED_AGAIN
    return ContinuationApiStatus.RESUMED_COMPLETED
