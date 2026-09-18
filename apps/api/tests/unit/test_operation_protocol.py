from __future__ import annotations

from app.agents.protocol import (
    NativeToolCallProtocolError,
    build_tool_result_messages,
    parse_llm_response,
    parse_native_tool_calls,
)
import pytest


def test_parse_native_tool_calls_keeps_same_operation_with_different_arguments():
    response = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "collection.info",
                                "arguments": '{"collection_slug":"alpha"}',
                            },
                        },
                        {
                            "id": "call-2",
                            "function": {
                                "name": "collection.info",
                                "arguments": '{"collection_slug":"beta"}',
                            },
                        },
                    ],
                }
            }
        ]
    }

    parsed = parse_native_tool_calls(response)

    assert parsed is not None
    assert parsed.has_tool_calls is True
    assert len(parsed.tool_calls) == 2
    assert [call.id for call in parsed.tool_calls] == ["call-1", "call-2"]
    assert parsed.tool_calls[0].arguments == {"collection_slug": "alpha"}
    assert parsed.tool_calls[1].arguments == {"collection_slug": "beta"}

    raw_tool_calls = response["choices"][0]["message"]["tool_calls"]
    messages = build_tool_result_messages(
        [(parsed.tool_calls[0], "alpha result"), (parsed.tool_calls[1], "beta result")],
        raw_tool_calls,
    )
    assert [message["tool_call_id"] for message in messages] == ["call-1", "call-2"]


def test_parse_native_tool_calls_keeps_duplicate_arguments_for_provider_correlation():
    response = {
        "choices": [{"message": {"tool_calls": [
            {"id": "call-1", "function": {"name": "collection.info", "arguments": '{"collection_slug":"alpha"}'}},
            {"id": "call-2", "function": {"name": "collection.info", "arguments": '{"collection_slug":"alpha"}'}},
        ]}}],
    }

    parsed = parse_native_tool_calls(response)

    assert parsed is not None
    assert [call.id for call in parsed.tool_calls] == ["call-1", "call-2"]


def test_parse_native_tool_calls_rejects_invalid_arguments_or_missing_provider_id():
    malformed_arguments = {
        "choices": [{"message": {"tool_calls": [{
            "id": "call-1",
            "function": {"name": "collection.info", "arguments": "{not-json"},
        }]}}],
    }
    missing_id = {
        "choices": [{"message": {"tool_calls": [{
            "function": {"name": "collection.info", "arguments": "{}"},
        }]}}],
    }

    with pytest.raises(NativeToolCallProtocolError):
        parse_native_tool_calls(malformed_arguments)
    with pytest.raises(NativeToolCallProtocolError):
        parse_native_tool_calls(missing_id)


def test_parse_llm_response_prefers_tool_call_protocol():
    parsed = parse_llm_response(
        """```tool_call
{
  "tool": "collection.info",
  "arguments": {
    "collection_slug": "template"
  }
}
```"""
    )

    assert parsed.has_tool_calls is True
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].tool_name == "collection.info"
    assert parsed.tool_calls[0].arguments == {"collection_slug": "template"}
