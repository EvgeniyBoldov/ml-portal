from app.agents.protocol import build_operations_prompt
from app.agents.runtime.prompt_assembler import PromptAssembler


def test_build_operations_prompt_uses_default_mandatory_rules():
    prompt = build_operations_prompt([{"type": "function", "function": {"name": "x", "parameters": {}}}])
    assert "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА" in prompt


def test_build_operations_prompt_uses_override_rules_text():
    prompt = build_operations_prompt(
        [{"type": "function", "function": {"name": "x", "parameters": {}}}],
        mandatory_rules_text="CUSTOM RULES BLOCK",
    )
    assert "CUSTOM RULES BLOCK" in prompt
    assert "MANDATORY RULES" not in prompt


def test_prompt_assembler_resolves_operations_rules_override_priority():
    assembler = PromptAssembler()
    platform = {"operations_rules_text": "platform"}
    sandbox = {"operations_rules_text": "sandbox"}
    assert (
        assembler._resolve_operations_rules_override(
            platform_config=platform,
            sandbox_overrides=sandbox,
        )
        == "sandbox"
    )
