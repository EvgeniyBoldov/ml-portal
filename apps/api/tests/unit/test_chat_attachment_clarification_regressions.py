from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.runtime.agent_executor import AgentExecutor
from app.runtime.contracts import AttachmentContext, AttachmentRef
from app.runtime.orchestrator_contracts import TaskRequest
from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision
from app.services.chat_context_service import ChatContextService


@pytest.mark.asyncio
async def test_loaded_artifacts_are_typed_and_readable_by_followup_stream():
    artifact_id = str(uuid4())
    repository = SimpleNamespace(get_head=AsyncMock(return_value=None), active_items_by_kind=AsyncMock(return_value=[
        SimpleNamespace(kind="artifact_ref", item_key=artifact_id, payload={"artifact_id": artifact_id}),
        SimpleNamespace(kind="open_loop", item_key="clarify", payload={"status": "waiting", "user_message": "Какой раздел?"}),
    ]))
    references = SimpleNamespace(resolve_many=AsyncMock(return_value={artifact_id: SimpleNamespace(
        file_name="document.pdf", content_type="application/pdf", size_bytes=1000)}))
    with patch("app.services.chat_context_service.ChatContextRepository", return_value=repository), \
         patch("app.services.chat_context_service.ChatArtifactReferenceService", return_value=references):
        snapshot = await ChatContextService(AsyncMock(), None, None).load_snapshot(
            chat_id=str(uuid4()), owner_id=str(uuid4()), tenant_id=str(uuid4()))
    assert snapshot.artifacts[0].artifact_id == artifact_id
    assert snapshot.open_loops[0].user_message == "Какой раздел?"


@pytest.mark.asyncio
async def test_preflight_never_echoes_original_request_as_clarification():
    preflight = TurnPreflight(session=AsyncMock(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(value=TurnPreflightDecision(
        route="clarify", clarification={"question": "Что скажешь о вложении?",
            "direct_answer_reason": "The user can provide the missing choice"})))
    decision = await preflight.decide(user_request="что скажешь о вложении?", mechanical_lookup={})
    assert decision.route == "planner"


@pytest.mark.asyncio
async def test_preflight_receives_current_file_and_routes_file_reading_to_planner():
    preflight = TurnPreflight(session=AsyncMock(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(value=TurnPreflightDecision(
        route="clarify", clarification={"question": "Прикрепите файл", "direct_answer_reason": "Need the file"})))
    attachment = AttachmentContext(ref=AttachmentRef(artifact_id=str(uuid4()), file_name="report.txt"),
        snippet="Annual report, revenue increased", snippet_status="ready", readable=True)
    decision = await preflight.decide(user_request="что скажешь о вложении?", mechanical_lookup={}, attachments=[attachment])
    assert decision.route == "planner"
    assert preflight._llm.invoke.await_args.kwargs["payload"]["datastore"]["items"][0]["artifact_id"] == attachment.ref.artifact_id


def test_agent_receives_only_attachment_metadata_and_must_read_contents():
    task = TaskRequest(task_id="read", executor="worker", intent="read file", instructions="Read the report")
    attachment = {
        "ref": {"artifact_id": str(uuid4()), "file_name": "report.pdf",
                "origin": {"kind": "rag_document", "source_type": "rag_document"},
                "description": "Quarterly report"},
        "snippet_status": "ready",
        "snippet": "Verification code: ATTACHMENT_7391",
    }
    message = AgentExecutor._build_sub_messages([], task, "read the report", attachments=[attachment])[-1]["content"]

    assert "ATTACHMENT_7391" not in message
    assert '"kind": "rag_document"' in message
    assert "Quarterly report" in message
    # Tool availability is supplied by the agent contract, not duplicated in
    # the task text. This projection only carries safe attachment metadata.
    assert "file.read" not in message


def test_repeating_inherited_task_scopes_requires_no_new_scope_rationale():
    from app.runtime.orchestrator import GraphOrchestrator
    from app.runtime.orchestrator_contracts import IterationProposal, PlannedTask
    proposal = IterationProposal(tasks=[PlannedTask(task_id="read", executor="secretary", intent="read file",
        instructions="read file", scope_keys=["company"])], terminal="planner")
    compiled = GraphOrchestrator._compile(proposal, [{"slug": "secretary"}], {"tasks": [], "needs": []},
        {"selected": [{"key": "company"}], "ceiling_keys": ["company"]})
    assert compiled.tasks[0].scope_context["keys"] == ["company"]


def test_clarification_history_preserves_answers_across_three_pauses():
    from app.runtime.pipeline import _build_continuation_state
    from app.runtime.contracts import PipelineRequest
    request = PipelineRequest(request_text="Таблица", user_id=str(uuid4()), tenant_id=str(uuid4()))
    state = _build_continuation_state(request, {"original_goal": "Отчёт", "resume_action": "input",
        "user_input": "Таблица", "paused_context": {"question": "Формат?", "clarification_history": [
            {"question": "Проект?", "answer": "Альфа"}, {"question": "Период?", "answer": "Ноябрь"}]}})
    assert [item["answer"] for item in state["clarification_history"]] == ["Альфа", "Ноябрь", "Таблица"]
    assert state["original_goal"] == "Отчёт"


def test_preflight_rejects_any_already_answered_question_but_allows_new_question():
    history = {"clarification_history": [{"question": "Какой проект?", "answer": "Альфа"}],
               "original_goal": "Подготовить отчёт"}
    assert TurnPreflight._repeats_answered_question("Какой проект?", "Ноябрь", history)
    assert not TurnPreflight._repeats_answered_question("Какой формат?", "Ноябрь", history)


@pytest.mark.asyncio
async def test_turn_attachment_context_contains_passport_without_reading_file_text():
    from app.services.chat_attachment_service import ChatAttachmentService
    artifact_id = str(uuid4())
    reference = SimpleNamespace(id=artifact_id, display_name="test.txt", content_type="text/plain",
        size_bytes=100, metadata_snapshot={"status": "uploaded"})
    references = SimpleNamespace(get_reference=AsyncMock(return_value=reference), manifest=lambda _: {
        "origin": {"kind": "user_upload", "source_id": "source-1"}, "description": None})
    representation = SimpleNamespace(metadata=AsyncMock(return_value={"status": "unread"}))
    with patch("app.services.chat_attachment_service.ChatArtifactReferenceService", return_value=references), \
         patch("app.services.artifact_representation_service.ArtifactRepresentationService", return_value=representation):
        values = await ChatAttachmentService(AsyncMock()).build_runtime_artifact_contexts(
            artifact_ids=[artifact_id], chat_id=str(uuid4()), owner_id=str(uuid4()))
    assert values[0].snippet == ""
    assert values[0].snippet_status == "unread"
    assert values[0].ref.origin["kind"] == "user_upload"
    representation.metadata.assert_awaited_once_with(artifact_id)


@pytest.mark.parametrize("extension,content", [("pdf", b"not a pdf"), ("txt", b"MZ\x00binary"),
    ("docx", b"not zip"), ("xlsx", b"not zip"), ("txt", b"binary\x00payload")])
def test_content_validation_rejects_mislabeled_files(extension, content):
    from app.services.upload_intake_policy import UploadIntakePolicy
    from app.core.exceptions import UploadValidationError
    with pytest.raises(UploadValidationError):
        UploadIntakePolicy.validate_chat_content(content, extension=extension)


@pytest.mark.asyncio
async def test_chat_upload_read_is_bounded_by_policy_limit():
    from app.services.chat_attachment_service import ChatAttachmentService
    from app.services.upload_intake_policy import ChatUploadTooLargeError
    service = ChatAttachmentService(AsyncMock())
    service.get_upload_policy = AsyncMock(return_value=SimpleNamespace(max_bytes=10, allowed_extensions=["txt"]))
    file = SimpleNamespace(filename="notes.txt", content_type="text/plain", read=AsyncMock(return_value=b"x"*11))
    with pytest.raises(ChatUploadTooLargeError):
        await service.upload_attachment(chat_id=str(uuid4()), owner_id=str(uuid4()), file=file)
    file.read.assert_awaited_once_with(11)
