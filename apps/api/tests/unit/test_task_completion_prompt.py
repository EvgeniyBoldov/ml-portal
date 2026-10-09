import json

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.orchestrator_contracts import TaskRequest
from app.runtime.task_completion_prompt import build_task_completion_prompt


@pytest.mark.parametrize("mode", ["any", "text", "structured", "artifact"])
def test_backend_prompt_publishes_universal_protocol_and_presentation_hint(mode):
    request = TaskRequest(task_id="task", executor="agent", intent="read", instructions="read",
                          response_spec={"mode": mode, "schema": {"type": "string"}})
    prompt = build_task_completion_prompt(request)
    presentation_line = next(line for line in prompt.splitlines() if line.startswith("Requested presentation"))
    assert json.loads(presentation_line.split(": ", 1)[1])["mode"] == mode
    assert "structured_response" in prompt
    assert "result.read" in prompt
    assert '"coverage"' not in prompt
    assert "query_call_ids" not in prompt


def test_structured_data_needs_no_output_slot_wrapper_or_schema_repair():
    request = TaskRequest(task_id="task", executor="agent", intent="read", instructions="read",
                          response_spec={"mode": "structured", "schema": {"type": "string"}})
    payload = {"completion": "fulfilled", "answer": "Device found; schema differs",
               "structured_response": {"hostname": "IR-224X-00955", "ip": None}}
    assert AgentExecutor._terminal_validation_errors(json.dumps(payload), task=request, verified={}) == []
