"""
Chat Turn State Machine — формальная модель состояний одного чат-тёрна.

Гарантирует:
- Переходы между состояниями валидны
- Каждый тёрн проходит через canonical lifecycle
- Невалидные переходы логируются как warning (не crash — graceful degradation)

Canonical lifecycle:
  INIT → USER_PERSISTED → CONTEXT_LOADED → TRIAGE_COMPLETE →
  EXECUTION_STARTED → [DELTA_STREAMING | PAUSED] → FINAL_PERSISTED → COMPLETED
                                                  ↘ ERROR (from any state)

Usage in ChatStreamService:
    turn = ChatTurnState()
    turn.transition(TurnPhase.USER_PERSISTED)
    ...
    turn.transition(TurnPhase.COMPLETED)
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class TurnPhase(str, Enum):
    """Phases of a single chat turn."""
    INIT = "init"
    USER_PERSISTED = "user_persisted"
    CONTEXT_LOADED = "context_loaded"
    TRIAGE_COMPLETE = "triage_complete"
    EXECUTION_STARTED = "execution_started"
    DELTA_STREAMING = "delta_streaming"
    PAUSED = "paused"
    FINAL_PERSISTED = "final_persisted"
    COMPLETED = "completed"
    ERROR = "error"


# Valid transitions: from_phase -> set of allowed to_phases
VALID_TRANSITIONS: Dict[TurnPhase, FrozenSet[TurnPhase]] = {
    TurnPhase.INIT: frozenset({
        TurnPhase.USER_PERSISTED,
        TurnPhase.ERROR,
    }),
    TurnPhase.USER_PERSISTED: frozenset({
        TurnPhase.CONTEXT_LOADED,
        TurnPhase.ERROR,
    }),
    TurnPhase.CONTEXT_LOADED: frozenset({
        TurnPhase.TRIAGE_COMPLETE,
        TurnPhase.EXECUTION_STARTED,  # skip triage for direct agent
        TurnPhase.ERROR,
    }),
    TurnPhase.TRIAGE_COMPLETE: frozenset({
        TurnPhase.EXECUTION_STARTED,
        TurnPhase.ERROR,
    }),
    TurnPhase.EXECUTION_STARTED: frozenset({
        TurnPhase.DELTA_STREAMING,
        TurnPhase.PAUSED,
        TurnPhase.FINAL_PERSISTED,  # no-delta short answer
        TurnPhase.ERROR,
    }),
    TurnPhase.DELTA_STREAMING: frozenset({
        TurnPhase.DELTA_STREAMING,  # multiple deltas
        TurnPhase.PAUSED,
        TurnPhase.FINAL_PERSISTED,
        TurnPhase.ERROR,
    }),
    TurnPhase.PAUSED: frozenset({
        TurnPhase.COMPLETED,  # stop event is terminal for this turn
        TurnPhase.ERROR,
    }),
    TurnPhase.FINAL_PERSISTED: frozenset({
        TurnPhase.COMPLETED,
        TurnPhase.ERROR,
    }),
    TurnPhase.COMPLETED: frozenset(),  # terminal
    TurnPhase.ERROR: frozenset(),  # terminal
}


class ChatTurnState:
    """Tracks and validates state transitions for a single chat turn."""

    __slots__ = ("_phase", "_chat_id", "_request_id")

    def __init__(self, chat_id: Optional[str] = None, request_id: Optional[str] = None):
        self._phase = TurnPhase.INIT
        self._chat_id = chat_id
        self._request_id = request_id

    @property
    def phase(self) -> TurnPhase:
        return self._phase

    @property
    def is_terminal(self) -> bool:
        return self._phase in (TurnPhase.COMPLETED, TurnPhase.ERROR)

    def transition(self, to: TurnPhase) -> bool:
        """Attempt a state transition.

        Returns True if transition is valid.
        Logs warning and still transitions on invalid moves (graceful degradation).
        """
        allowed = VALID_TRANSITIONS.get(self._phase, frozenset())

        if to not in allowed:
            logger.warning(
                "invalid_turn_transition",
                extra={
                    "from": self._phase.value,
                    "to": to.value,
                    "chat_id": self._chat_id,
                    "request_id": self._request_id,
                },
            )
            # Still transition — we don't want to crash the chat over a state bug
            self._phase = to
            return False

        self._phase = to
        return True

    def force_error(self) -> None:
        """Force transition to ERROR from any state."""
        self._phase = TurnPhase.ERROR

    def __repr__(self) -> str:
        return f"ChatTurnState(phase={self._phase.value}, chat={self._chat_id})"
