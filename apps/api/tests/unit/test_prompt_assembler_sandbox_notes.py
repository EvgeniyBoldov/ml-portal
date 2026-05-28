from types import SimpleNamespace

from app.agents.runtime.prompt_assembler import PromptAssembler


def _exec_request() -> SimpleNamespace:
    return SimpleNamespace(
        policy_data={},
        limit_data={},
        resolved_data_instances=[],
    )


def test_constraints_prompt_hides_sandbox_notes_by_default():
    assembler = PromptAssembler()
    text = assembler.assemble_constraints_prompt(
        exec_request=_exec_request(),
        policy_limits=SimpleNamespace(
            max_steps=1,
            max_tool_calls_total=1,
            max_wall_time_ms=1,
            tool_timeout_ms=1,
            max_retries=1,
            streaming_enabled=True,
            citations_required=False,
            allow_parallel_tool_calls=True,
        ),
        platform_config={},
        sandbox_overrides={"prompt": "x", "orchestration": {"a": 1}},
    )
    assert "Заметки sandbox" not in text


def test_constraints_prompt_includes_sandbox_notes_when_flag_enabled():
    assembler = PromptAssembler()
    text = assembler.assemble_constraints_prompt(
        exec_request=_exec_request(),
        policy_limits=SimpleNamespace(
            max_steps=1,
            max_tool_calls_total=1,
            max_wall_time_ms=1,
            tool_timeout_ms=1,
            max_retries=1,
            streaming_enabled=True,
            citations_required=False,
            allow_parallel_tool_calls=True,
        ),
        platform_config={},
        sandbox_overrides={
            "include_sandbox_notes_in_prompt": True,
            "prompt": "x",
            "orchestration": {"a": 1},
        },
    )
    assert "Заметки sandbox" in text
