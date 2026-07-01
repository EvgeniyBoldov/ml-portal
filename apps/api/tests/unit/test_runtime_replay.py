from app.runtime.replay import RuntimeReplayRunner


def test_replay_successful_trace():
    trace_pack = {
        "trace_pack_version": "runtime.trace_pack.v2",
        "timeline": [
            {"step_number": 0, "step_type": "tool_call"},
            {"step_number": 1, "step_type": "tool_result"},
        ],
        "tool_io": [
            {"step_type": "tool_call", "tool": "collection.search"},
            {"step_type": "tool_result", "tool": "collection.search", "output": {"hits": 1}},
        ],
    }

    result = RuntimeReplayRunner().replay(trace_pack)
    assert result.ok is True
    assert result.reason == "replay_ok"


def test_replay_fails_when_tool_output_missing():
    trace_pack = {
        "trace_pack_version": "runtime.trace_pack.v2",
        "timeline": [{"step_number": 0, "step_type": "tool_call"}],
        "tool_io": [{"step_type": "tool_call", "tool": "collection.search"}],
    }

    result = RuntimeReplayRunner().replay(trace_pack)
    assert result.ok is False
    assert result.reason == "missing_tool_output"


def test_replay_blocks_destructive_operation_by_default():
    trace_pack = {
        "trace_pack_version": "runtime.trace_pack.v2",
        "timeline": [{"step_number": 0, "step_type": "tool_call"}],
        "tool_io": [
            {
                "step_type": "tool_call",
                "tool": "instance.system.delete",
                "risk_level": "destructive",
            }
        ],
    }

    result = RuntimeReplayRunner().replay(trace_pack)
    assert result.ok is False
    assert result.reason == "destructive_operation_blocked"
