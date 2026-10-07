import json

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.orchestrator_contracts import TaskRequest
from app.runtime.task_completion_prompt import build_task_completion_prompt, output_slot_example


def task(fulfillment="task_result"):
    return TaskRequest(
        task_id="task", executor="agent", intent="Read device", instructions="Read device",
        expected_outputs=[{
            "key": "device", "description": "Device", "schema": {"type": "object"},
            "fulfillment": fulfillment,
            "receipt_operations": ["netbox_get_device"] if fulfillment == "verified_receipt" else [],
        }],
    )


@pytest.mark.parametrize("fulfillment,kind", [
    ("task_result", "value"), ("verified_receipt", "evidence"), ("artifact", "artifact"),
])
def test_backend_contract_uses_current_task_keys_and_fulfillment(fulfillment, kind):
    request = task(fulfillment)
    prompt = build_task_completion_prompt(request)
    example_start = prompt.index("{", prompt.index("Структурный пример для текущей задачи"))
    example, _ = json.JSONDecoder().raw_decode(prompt[example_start:])
    assert set(example["outputs"]) == {"device"}
    assert example["outputs"]["device"]["kind"] == kind
    assert example["outputs"]["device"] == output_slot_example(request, "device")
    assert "query_call_ids" in prompt
    assert "SQL call_id" in prompt
    assert "schema каждого output описывает содержимое value" in prompt


def test_dcbox_raw_object_gets_actionable_slot_repair_and_wrapped_result_validates():
    request = task()
    payload = {"completion": "fulfilled", "report": "Found device",
               "outputs": {"device": {"hostname": "IR-224X-00955"}}}
    errors = AgentExecutor._terminal_validation_errors(json.dumps(payload), task=request, verified={})
    assert len(errors) == 1
    assert "outputs.device" in errors[0]
    assert '"kind": "value"' in errors[0]
    assert "внутрь value" in errors[0]
    payload["outputs"]["device"] = {"kind": "value", "value": payload["outputs"]["device"]}
    assert AgentExecutor._terminal_validation_errors(json.dumps(payload), task=request, verified={}) == []
