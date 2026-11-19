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


def test_legacy_agent_examples_and_repair_point_to_one_completion_contract():
    request = TaskRequest(task_id="task", executor="agent", intent="read", instructions="read")
    legacy = '{"completion":"fulfilled","report":"found","outputs":{"pages":["DCBox"]}}'
    prompt = AgentExecutor._with_terminal_contract_prompt(
        f"# Rules\nRead the complete page.\n\n# Output Format\n{legacy}\n\n# Examples\n{legacy}\n\n# Safety\nRead-only.",
        request,
    )
    assert "Read the complete page." in prompt and "Read-only." in prompt
    assert legacy not in prompt
    errors = AgentExecutor._terminal_validation_errors(legacy, task=request, verified={})
    assert len(errors) == 1 and "structured_response" in errors[0]
    assert "kind=value" not in errors[0]
