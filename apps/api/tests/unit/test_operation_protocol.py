from __future__ import annotations

from app.agents.protocol import parse_llm_response, parse_native_tool_calls


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
    assert parsed.tool_calls[0].arguments == {"collection_slug": "alpha"}
    assert parsed.tool_calls[1].arguments == {"collection_slug": "beta"}


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
