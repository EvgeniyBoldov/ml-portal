from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.runtime.llm import LLMAdapter
from app.agents.runtime.llm_errors import (
    LLMRequestTooLargeError,
    LLMToolCallingUnsupportedError,
    classify_provider_error,
)


def _provider_error() -> Exception:
    failed_generation = json.dumps({
        "name": "container.exec",
        "arguments": {"cmd": ["bash", "-lc", "python - << 'PY'\nprint('')\nPY"]},
    }).replace("'", "\\'")
    return SimpleNamespace(
        body={
            "error": {
                "code": "tool_use_failed",
                "message": "Tool choice is none, but model called a tool",
                "failed_generation": failed_generation,
            }
        },
        __str__=lambda self: "tool_choice=none tool_use_failed",
    )


def test_coerces_groq_failed_generation_with_escaped_single_quotes() -> None:
    fallback = LLMAdapter._coerce_tool_choice_error_to_tool_call(_provider_error())

    assert fallback is not None
    assert '"tool": "container.exec"' in fallback


def test_coerces_same_payload_to_native_tool_call() -> None:
    fallback = LLMAdapter._coerce_tool_choice_error_to_native_response(_provider_error())

    assert fallback is not None
    function = fallback["choices"][0]["message"]["tool_calls"][0]["function"]
    assert function["name"] == "container.exec"


def test_classifies_tool_choice_mismatch_for_plaintext_fallback() -> None:
    classified = classify_provider_error(_provider_error())

    assert isinstance(classified, LLMToolCallingUnsupportedError)
    assert classified.code == "llm_tool_calling_unsupported"


def test_classifies_provider_token_limit_without_retry() -> None:
    error = SimpleNamespace(
        body={"error": {"code": "rate_limit_exceeded", "message": "Requested 11283 tokens per minute"}},
        __str__=lambda self: "Error code: 413",
    )

    classified = classify_provider_error(error)

    assert isinstance(classified, LLMRequestTooLargeError)
    assert classified.retryable is False
