from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion,
    AgentExecutionResult,
    NeedSpec,
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
            needs=[NeedSpec(key="target", description="Target system")],
        ),
    )

    assert result.outcome is TaskOutcome.NEEDS_DEPENDENCY
    assert result.partial_completion == "Need the target system"


def test_agent_declared_output_does_not_satisfy_verified_receipt_contract() -> None:
    result = TaskAttemptResultReducer().reduce(
        request=_request(expected_outputs=[TaskOutputSpec(
            key="current_policy",
            description="Current policy",
            fulfillment=TaskOutputFulfillment.VERIFIED_RECEIPT,
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
