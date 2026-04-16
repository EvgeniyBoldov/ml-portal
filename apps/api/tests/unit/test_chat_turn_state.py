"""
Contract tests for Chat Turn State Machine.

Validates:
- Valid transitions proceed without warning
- Invalid transitions are logged but still proceed (graceful degradation)
- Terminal states block further transitions
- force_error works from any state
- Complete happy path lifecycle
"""
import pytest
from app.services.chat_turn_state import ChatTurnState, TurnPhase, VALID_TRANSITIONS


class TestValidTransitions:
    """All transitions defined in VALID_TRANSITIONS must succeed."""

    def test_all_valid_transitions_return_true(self):
        for from_phase, to_phases in VALID_TRANSITIONS.items():
            for to_phase in to_phases:
                turn = ChatTurnState(chat_id="test", request_id="req-1")
                turn._phase = from_phase  # Force state for testing
                result = turn.transition(to_phase)
                assert result is True, (
                    f"Expected valid transition {from_phase} -> {to_phase} to return True"
                )
                assert turn.phase == to_phase


class TestInvalidTransitions:
    """Invalid transitions should return False but still transition."""

    def test_init_to_completed_is_invalid(self):
        turn = ChatTurnState()
        result = turn.transition(TurnPhase.COMPLETED)
        assert result is False
        assert turn.phase == TurnPhase.COMPLETED  # Still transitions

    def test_user_persisted_to_execution_started_is_invalid(self):
        turn = ChatTurnState()
        turn._phase = TurnPhase.USER_PERSISTED
        result = turn.transition(TurnPhase.EXECUTION_STARTED)
        assert result is False


class TestTerminalStates:
    """Terminal states (COMPLETED, ERROR) have no outgoing transitions."""

    def test_completed_is_terminal(self):
        turn = ChatTurnState()
        turn._phase = TurnPhase.COMPLETED
        assert turn.is_terminal is True
        assert len(VALID_TRANSITIONS[TurnPhase.COMPLETED]) == 0

    def test_error_is_terminal(self):
        turn = ChatTurnState()
        turn._phase = TurnPhase.ERROR
        assert turn.is_terminal is True
        assert len(VALID_TRANSITIONS[TurnPhase.ERROR]) == 0


class TestForceError:
    """force_error must work from any state."""

    @pytest.mark.parametrize("phase", list(TurnPhase))
    def test_force_error_from_any_phase(self, phase):
        turn = ChatTurnState()
        turn._phase = phase
        turn.force_error()
        assert turn.phase == TurnPhase.ERROR
        assert turn.is_terminal is True


class TestHappyPathLifecycle:
    """Complete successful chat turn lifecycle."""

    def test_full_lifecycle(self):
        turn = ChatTurnState(chat_id="chat-1", request_id="req-1")

        assert turn.phase == TurnPhase.INIT
        assert not turn.is_terminal

        assert turn.transition(TurnPhase.USER_PERSISTED) is True
        assert turn.transition(TurnPhase.CONTEXT_LOADED) is True
        assert turn.transition(TurnPhase.EXECUTION_STARTED) is True
        assert turn.transition(TurnPhase.DELTA_STREAMING) is True
        assert turn.transition(TurnPhase.DELTA_STREAMING) is True  # multiple deltas
        assert turn.transition(TurnPhase.FINAL_PERSISTED) is True
        assert turn.transition(TurnPhase.COMPLETED) is True

        assert turn.is_terminal is True

    def test_error_during_execution(self):
        turn = ChatTurnState(chat_id="chat-2", request_id="req-2")

        assert turn.transition(TurnPhase.USER_PERSISTED) is True
        assert turn.transition(TurnPhase.CONTEXT_LOADED) is True
        assert turn.transition(TurnPhase.EXECUTION_STARTED) is True
        assert turn.transition(TurnPhase.ERROR) is True
        assert turn.is_terminal is True

    def test_paused_lifecycle(self):
        turn = ChatTurnState(chat_id="chat-3", request_id="req-3")

        assert turn.transition(TurnPhase.USER_PERSISTED) is True
        assert turn.transition(TurnPhase.CONTEXT_LOADED) is True
        assert turn.transition(TurnPhase.EXECUTION_STARTED) is True
        assert turn.transition(TurnPhase.DELTA_STREAMING) is True
        assert turn.transition(TurnPhase.PAUSED) is True
        assert turn.transition(TurnPhase.COMPLETED) is True
        assert turn.is_terminal is True

    def test_skip_triage(self):
        """Direct agent execution can skip TRIAGE_COMPLETE."""
        turn = ChatTurnState()

        assert turn.transition(TurnPhase.USER_PERSISTED) is True
        assert turn.transition(TurnPhase.CONTEXT_LOADED) is True
        assert turn.transition(TurnPhase.EXECUTION_STARTED) is True  # skip triage


class TestRepr:
    def test_repr(self):
        turn = ChatTurnState(chat_id="c-1")
        assert "init" in repr(turn)
        assert "c-1" in repr(turn)
