from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.runtime.llm import LLMAdapter


def _provider_error() -> Exception:
    failed_generation = json.dumps({
        "name": "container.exec",
        "arguments": {"cmd": ["bash", "-lc", "python - << 'PY'\nprint('')\nPY"]},
    }).replace("'", "\\'")
    return SimpleNamespace(
        body={
            "error": {
                "code": "tool_use_failed",
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
