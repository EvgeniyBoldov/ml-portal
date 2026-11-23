from app.agents.runtime.prompt_assembler import PromptAssembler


def test_constraints_prompt_hides_sandbox_notes_by_default():
    assembler = PromptAssembler()
    text = assembler.assemble_constraints_prompt(
        platform_config={},
        sandbox_overrides={"prompt": "x", "orchestration": {"a": 1}},
    )
    assert "Заметки sandbox" not in text


def test_constraints_prompt_includes_sandbox_notes_when_flag_enabled():
    assembler = PromptAssembler()
    text = assembler.assemble_constraints_prompt(
        platform_config={},
        sandbox_overrides={
            "include_sandbox_notes_in_prompt": True,
            "prompt": "x",
            "orchestration": {"a": 1},
        },
    )
    assert "Заметки sandbox" in text
