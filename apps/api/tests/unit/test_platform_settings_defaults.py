from types import SimpleNamespace

from app.services.platform_settings_defaults import (
    PLATFORM_INTENT_MESSAGES,
    PLATFORM_OPERATION_RULES_TEXT,
    PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION,
    PLATFORM_SYNTH_CHUNK_SIZE,
    PLATFORM_DEFAULT_MAX_ITERS,
    build_effective_platform_settings_payload,
    build_platform_runtime_config,
)


def test_build_effective_platform_settings_payload_uses_fallbacks_when_missing():
    payload = build_effective_platform_settings_payload(SimpleNamespace())

    assert payload["required_operation_retry_instruction"] == PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION
    assert payload["operations_rules_text"] == PLATFORM_OPERATION_RULES_TEXT
    assert payload["intent_messages"] == PLATFORM_INTENT_MESSAGES
    assert payload["default_max_iters"] == PLATFORM_DEFAULT_MAX_ITERS
    assert payload["synth_chunk_size"] == PLATFORM_SYNTH_CHUNK_SIZE


def test_build_platform_runtime_config_uses_same_fallbacks():
    config = build_platform_runtime_config(SimpleNamespace())

    assert config["required_operation_retry_instruction"] == PLATFORM_REQUIRED_OPERATION_RETRY_INSTRUCTION
    assert config["operations_rules_text"] == PLATFORM_OPERATION_RULES_TEXT
    assert config["intent_messages"] == PLATFORM_INTENT_MESSAGES
    assert config["default_max_iters"] == PLATFORM_DEFAULT_MAX_ITERS
    assert config["runtime"]["synth_chunk_size"] == PLATFORM_SYNTH_CHUNK_SIZE
