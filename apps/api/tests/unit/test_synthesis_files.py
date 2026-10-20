from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.agents.context import ToolContext
from app.runtime.run_context import RunContext
from app.runtime.synthesis_files import FileSynthesisOutput, generate_file_answer


@pytest.fixture
def setup(monkeypatch):
    from app.runtime import synthesis_files as module
    session = MagicMock()

    @asynccontextmanager
    async def nested():
        yield

    session.begin_nested = nested
    llm = AsyncMock(return_value=SimpleNamespace(value=FileSynthesisOutput(message="Готов файл", files=[
        {"filename": "example.py", "format": "py", "content": "print('hello')"}])))
    generate = AsyncMock(return_value=SimpleNamespace(artifact_id=str(uuid4()), file_name="example.py", content_type="text/x-python", size_bytes=14))
    monkeypatch.setattr(module, "StructuredLLMCall", lambda **_: SimpleNamespace(invoke=llm))
    monkeypatch.setattr(module, "FileGenerationService", lambda _: SimpleNamespace(generate=generate))
    passport = {"schema_version": 1, "artifact_id": "generated", "origin": {"kind": "agent_generated"},
                "file": {"name": "example.py"}, "description": None, "representation": None,
                "status": "generated", "attributes": {}}
    monkeypatch.setattr("app.services.chat_artifact_reference_service.ChatArtifactReferenceService",
        lambda _: SimpleNamespace(get_reference=AsyncMock(return_value=object()), manifest=lambda __: passport))
    monkeypatch.setattr(module, "OperationRouter", lambda _: SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(
        execution_graph={"file.generate": True}, resolved_operations=[]))))
    monkeypatch.setattr("app.services.runtime_run_context_service.RuntimeRunContextService.save", AsyncMock())
    state = SimpleNamespace(run_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), tenant_id=uuid4(), run_context=RunContext())
    kwargs = dict(session=session, llm_client=object(), state=state,
        context={"synthesis_brief": {"delivery": "files", "files": [{"filename": "example.py", "format": "py"}]}},
        prompt="Generate", ctx=ToolContext(user_id=state.user_id, tenant_id=state.tenant_id, chat_id=state.chat_id),
        synthesis_id=str(uuid4()), sandbox_overrides={}, budget_registry=None)
    return kwargs, generate, llm


@pytest.mark.asyncio
async def test_generated_file_becomes_verified_run_artifact(setup):
    kwargs, generate, llm = setup
    message, artifacts, events = await generate_file_answer(**kwargs)
    assert message == "Готов файл"
    assert artifacts == kwargs["state"].run_context.generated_artifacts
    assert artifacts[0]["file_name"] == "example.py"
    assert generate.await_args.kwargs["content"] == "print('hello')"
    assert [event.type.value for event in events] == ["tool_call", "tool_result"]
    assert str(UUID(events[0].data["call_id"])) == events[0].data["call_id"]
    assert llm.await_args.kwargs["schema"] is FileSynthesisOutput
    assert '"properties"' not in llm.await_args.kwargs["system_prompt"]
    assert "response_format" in llm.await_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_failed_file_never_publishes_success(setup):
    kwargs, generate, _ = setup
    generate.side_effect = ValueError("storage failed")
    with pytest.raises(ValueError):
        await generate_file_answer(**kwargs)
    assert kwargs["state"].run_context.generated_artifacts == []
    assert kwargs["state"].run_context.synthesis_message is None


@pytest.mark.asyncio
async def test_denied_generation_does_not_call_model_or_writer(setup):
    kwargs, generate, llm = setup
    kwargs["ctx"].denied_tools = ["file.generate"]
    with pytest.raises(ValueError):
        await generate_file_answer(**kwargs)
    llm.assert_not_awaited()
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_required_file_cannot_be_silently_renamed(setup):
    kwargs, generate, _ = setup
    kwargs["context"]["synthesis_brief"]["files"][0]["filename"] = "required.py"
    with pytest.raises(ValueError, match="deliverables"):
        await generate_file_answer(**kwargs)
    generate.assert_not_awaited()


def test_invalid_json_and_duplicate_filenames_are_rejected():
    for files in ([{"filename": "data.json", "format": "json", "content": "not JSON"}],
                  [{"filename": "a.txt", "format": "txt", "content": "a"}] * 2):
        with pytest.raises(ValidationError):
            FileSynthesisOutput(message="done", files=files)
