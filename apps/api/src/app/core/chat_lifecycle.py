"""Stable lifecycle and execution-stage vocabulary for chat turns."""
from __future__ import annotations

from enum import Enum


class ChatTurnStatus(str, Enum):
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatExecutionStage(str, Enum):
    PREPARING = "preparing"
    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    FINALIZING = "finalizing"


LEGACY_ACTIVE_STATUSES = ("started", "resumed")
ACTIVE_STATUSES = (ChatTurnStatus.RUNNING.value, *LEGACY_ACTIVE_STATUSES)
LEGACY_PAUSED_STATUSES = ("paused",)
WAITING_STATUSES = (
    ChatTurnStatus.WAITING_INPUT.value,
    ChatTurnStatus.WAITING_CONFIRMATION.value,
    *LEGACY_PAUSED_STATUSES,
)


def normalize_chat_turn_status(status: str, pause_status: str | None = None) -> str:
    """Project legacy database values into the stable public lifecycle."""
    value = str(status or "").strip().lower()
    if value in LEGACY_ACTIVE_STATUSES:
        return ChatTurnStatus.RUNNING.value
    if value == "paused":
        if pause_status == ChatTurnStatus.WAITING_CONFIRMATION.value:
            return ChatTurnStatus.WAITING_CONFIRMATION.value
        return ChatTurnStatus.WAITING_INPUT.value
    if value in {item.value for item in ChatTurnStatus}:
        return value
    return ChatTurnStatus.FAILED.value


def waiting_status_for_pause(pause_status: str | None) -> str:
    if pause_status == ChatTurnStatus.WAITING_CONFIRMATION.value:
        return ChatTurnStatus.WAITING_CONFIRMATION.value
    return ChatTurnStatus.WAITING_INPUT.value
