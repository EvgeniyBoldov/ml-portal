from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion,
    AgentExecutionResult,
    DiscoveredNeed,
    TaskOutputFulfillment,
    TaskOutputSpec,
    TaskOutputValue,
    TaskOutcome,
    TaskRequest,
)
from app.runtime.task_result_reducer import TaskAttemptResultReducer


def _request(**overrides):
    return TaskRequest(
        task_id="task",
        executor="agent",
        intent="answer",
        instructions="answer",
        **overrides,
    )


def _execution(**overrides):
    return AgentExecutionResult(
        completion=AgentExecutionCompletion.FULFILLED,
        description="Found the answer",
        **overrides,
    )


def test_allow_memory_fulfils_without_tool_receipt() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(key="answer", description="Answer")]),
        execution=_execution(outputs={"answer": TaskOutputValue(text="known fact")}),
    )

    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["answer"].text == "known fact"


def test_array_schema_validates_the_data_value_without_a_wrapper() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="jira_tasks",
            description="Open Jira tasks",
            json_schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["key", "status", "summary"],
                    "properties": {
                        "key": {"type": "string"},
                        "status": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
            },
        )]),
        execution=_execution(outputs={"jira_tasks": TaskOutputValue(data=[{
            "key": "NIMS-3334", "status": "В работе", "summary": "Интеграция MLFlow",
        }])}),
    )

    assert result.outcome is TaskOutcome.COMPLETED


def test_array_schema_rejects_a_shape_that_wraps_the_array() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="jira_tasks",
            description="Open Jira tasks",
            json_schema={"type": "array"},
        )]),
        execution=_execution(outputs={"jira_tasks": TaskOutputValue(data={"tasks": []})}),
    )

    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "output_schema_invalid"


def test_require_retrieval_keeps_partial_result_when_no_receipt_exists() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(freshness_policy="require_retrieval"),
        execution=_execution(),
    )

    assert result.outcome is TaskOutcome.NEEDS_DEPENDENCY
    assert result.reason_code == "fresh_retrieval_missing"
    assert result.needs[0].key == "fresh_retrieval"


def test_verified_retrieval_receipt_permits_fresh_completion() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(freshness_policy="require_retrieval"),
        execution=_execution(verified={"fresh_retrieval": True, "receipts": [{"call_id": "1"}]}),
    )

    assert result.outcome is TaskOutcome.COMPLETED


def test_need_is_successful_execution_but_waiting_task_result() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(),
        execution=AgentExecutionResult(
            completion=AgentExecutionCompletion.NEEDS,
            description="Need the target system",
            needs=[DiscoveredNeed(ref="target", key="target", description="Target system")],
        ),
    )

    assert result.outcome is TaskOutcome.NEEDS_DEPENDENCY
    assert result.description == "Need the target system"


def test_agent_declared_output_does_not_satisfy_verified_receipt_contract() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="current_policy",
            description="Current policy",
            fulfillment=TaskOutputFulfillment.VERIFIED_RECEIPT,
            receipt_operations=["collection.document.search"],
        )]),
        execution=_execution(outputs={"current_policy": TaskOutputValue(text="invented")}),
    )

    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "required_output_missing"


def test_verified_artifact_is_runtime_owned_not_agent_declared() -> None:
    artifact = {"artifact_id": "artifact-1", "file_name": "report.xlsx"}
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="report",
            description="Generated report",
            fulfillment=TaskOutputFulfillment.ARTIFACT,
        )]),
        execution=_execution(verified={"artifacts": [artifact]}),
    )

    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["report"].artifacts == [artifact]


def test_declared_artifact_is_replaced_by_verified_ledger_artifact() -> None:
    verified = {"artifact_id": "artifact-verified", "file_name": "report.xlsx"}
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="report",
            description="Generated report",
            fulfillment=TaskOutputFulfillment.ARTIFACT,
        )]),
        execution=_execution(
            outputs={"report": TaskOutputValue(artifacts=[{"artifact_id": "invented"}])},
            verified={"artifacts": [verified]},
        ),
    )

    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["report"].artifacts == [verified]


def test_declared_artifact_without_verified_ledger_artifact_does_not_fulfil_contract() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="report",
            description="Generated report",
            fulfillment=TaskOutputFulfillment.ARTIFACT,
        )]),
        execution=_execution(outputs={"report": TaskOutputValue(artifacts=[{"artifact_id": "invented"}])}),
    )

    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "required_output_missing"
