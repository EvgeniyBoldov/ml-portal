from __future__ import annotations

from app.runtime.agent_executor import AgentExecutor


def test_unwrap_operation_result_payload_prefers_nested_data():
    payload = AgentExecutor._unwrap_operation_result_payload(
        {
            "result": {
                "data": {
                    "file_id": "chatatt_1",
                    "file_name": "report.txt",
                },
                "call_id": "c1",
                "success": True,
                "operation_slug": "file.generate",
            }
        }
    )

    assert payload == {
        "file_id": "chatatt_1",
        "file_name": "report.txt",
    }


def test_unwrap_operation_result_payload_falls_back_to_direct_data():
    payload = AgentExecutor._unwrap_operation_result_payload(
        {
            "data": {
                "source_id": "doc-1",
                "source_name": "Регламент",
            }
        }
    )

    assert payload == {
        "source_id": "doc-1",
        "source_name": "Регламент",
    }
