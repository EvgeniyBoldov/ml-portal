"""Structured file-answer generation; persistence belongs to the owning session."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.context import ToolContext
from app.core.config import get_settings
from app.agents.operation_router import OperationRouter
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall
from app.models.system_llm_role import SystemLLMRoleType
from app.services.file_formats import FileCodecRegistry
from app.services.file_generation_service import FileGenerationService
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.core.http.clients import LLMClientProtocol
    from app.runtime.turn_state import RuntimeTurnState
    from app.runtime.budgets import BudgetRegistry


class FileDeliverable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1)
    format: str = Field(json_schema_extra={"enum": list(FileCodecRegistry.supported_formats())})
    purpose: str = ""

    @field_validator("format")
    @classmethod
    def supported_format(cls, value: str) -> str:
        FileCodecRegistry.get(value)
        return value


class GeneratedFileBody(FileDeliverable):
    content: str = Field(min_length=1)


class FileSynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1)
    files: list[GeneratedFileBody] = Field(min_length=1, max_length=get_settings().SYNTHESIS_MAX_FILES)

    @field_validator("files")
    @classmethod
    def valid_files(cls, files: list[GeneratedFileBody]) -> list[GeneratedFileBody]:
        names = set()
        for item in files:
            encoded = FileCodecRegistry.get(item.format).encode(item.content, item.filename)
            if encoded.filename in names:
                raise ValueError("Duplicate output filename")
            names.add(encoded.filename)
        return files


async def generate_file_answer(
    *, session: AsyncSession, llm_client: LLMClientProtocol, state: RuntimeTurnState,
    context: dict[str, Any], prompt: str, ctx: ToolContext | None, synthesis_id: str,
    sandbox_overrides: dict[str, Any] | None, budget_registry: BudgetRegistry | None,
    events: list[RuntimeEvent] | None = None,
) -> tuple[str, list[dict[str, Any]], list[RuntimeEvent]]:
    if ctx is None or not ctx.chat_id or not ctx.user_id or "file.generate" in ctx.denied_tools:
        raise ValueError("File generation is unavailable")
    resolved = await OperationRouter(session).resolve(user_id=ctx.user_id, tenant_id=ctx.tenant_id,
        collection_ids=[], system_operation_slugs={"file.generate"})
    if any(getattr(op, "requires_confirmation", False) for op in resolved.resolved_operations):
        raise ValueError("File generation requires an execution confirmation")
    if not resolved.execution_graph.get("file.generate"):
        raise ValueError("File generation is not permitted")
    if state.run_context.synthesis_message and state.run_context.generated_artifacts:
        from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
        for artifact in state.run_context.generated_artifacts:
            await ChatArtifactReferenceService(session).resolve(artifact_id=artifact["artifact_id"],
                chat_id=str(ctx.chat_id), owner_id=str(ctx.user_id), tenant_id=ctx.tenant_id)
        return state.run_context.synthesis_message, state.run_context.generated_artifacts, []
    events = [] if events is None else events

    async def sink(event):
        events.append(event)

    result = await StructuredLLMCall(session=session, llm_client=llm_client).invoke(
        role=SystemLLMRoleType.SYNTHESIZER, payload=context, schema=FileSynthesisOutput,
        system_prompt=prompt + "\nReturn JSON matching this schema: " + json.dumps(FileSynthesisOutput.model_json_schema(), ensure_ascii=False) +
        "\nCreate the requested file bodies. message is the user-facing response after all files are saved. No download URLs.",
        chat_id=state.chat_id, user_id=state.user_id, tenant_id=state.tenant_id,
        trace_parent_entity_type="synthesis_run", trace_parent_entity_id=synthesis_id,
        sandbox_overrides=sandbox_overrides, budget_registry=budget_registry, budget_entity_id=synthesis_id,
        event_sink=sink)
    output = result.value
    requested = (context.get("synthesis_brief") or {}).get("files") or []
    expected = {FileCodecRegistry.normalize_filename(item["format"], item["filename"])
                for item in requested}
    actual = {FileCodecRegistry.normalize_filename(item.format, item.filename) for item in output.files}
    if expected and expected != actual:
        raise ValueError("Generated files do not match requested deliverables")
    artifacts = []
    previous_artifacts = state.run_context.generated_artifacts
    previous_message = state.run_context.synthesis_message
    try:
        async with session.begin_nested():
            for index, item in enumerate(output.files):
                call_id = str(uuid5(NAMESPACE_URL, f"{state.run_id}:synthesis-file:{index}"))
                events.append(RuntimeEvent.tool_call(tool="file.generate", call_id=call_id,
                    arguments={"filename": item.filename, "format": item.format},
                    parent_entity_type="synthesis_run", parent_entity_id=synthesis_id))
                try:
                    if budget_registry is not None:
                        budget_registry.consume(synthesis_id, "tool_calls", reason="file.generate")
                    artifact = await FileGenerationService(session).generate(chat_id=str(ctx.chat_id),
                        owner_id=str(ctx.user_id), filename=item.filename, format_name=item.format, content=item.content,
                        metadata={"root_run_id": str(state.run_id), "deliverable_key": str(index),
                                  "description": {"text": item.purpose[:600], "source": "model_inferred"}})
                    from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
                    artifact_service = ChatArtifactReferenceService(session)
                    reference = await artifact_service.get_reference(
                        artifact_id=artifact.artifact_id, chat_id=str(ctx.chat_id), owner_id=str(ctx.user_id))
                    passport = artifact_service.manifest(reference)
                except Exception:
                    events.append(RuntimeEvent.tool_result(tool="file.generate", call_id=call_id,
                        success=False, data={}, error_code="file_generation_failed",
                        safe_message="Не удалось сохранить файл ответа",
                        parent_entity_type="synthesis_run", parent_entity_id=synthesis_id))
                    raise
                dto = {"artifact_id": artifact.artifact_id, "file_name": artifact.file_name,
                       "content_type": artifact.content_type, "size_bytes": artifact.size_bytes, "role": "generated",
                       "description": item.purpose[:600], "status": "generated", "artifact": passport}
                artifacts.append(dto)
                events.append(RuntimeEvent.tool_result(tool="file.generate", call_id=call_id, success=True, data=dto,
                    parent_entity_type="synthesis_run", parent_entity_id=synthesis_id))
            state.run_context.generated_artifacts = artifacts
            state.run_context.synthesis_message = output.message
            from app.services.runtime_run_context_service import RuntimeRunContextService
            await RuntimeRunContextService(session).save(run_id=str(state.run_id), chat_id=str(state.chat_id),
                owner_id=str(state.user_id), branch_id=(sandbox_overrides or {}).get("sandbox_branch_id"),
                context=state.run_context)
    except BaseException:
        state.run_context.generated_artifacts = previous_artifacts
        state.run_context.synthesis_message = previous_message
        raise
    return output.message, artifacts, events
