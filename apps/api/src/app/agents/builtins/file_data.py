"""Document-local reads and opt-in search over canonical chat artifacts."""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger
from app.schemas.file_data import (
    FileDataReadInput, FileDataReadOutput, FileDataPrepareInput, FileDataPrepareOutput,
    FileDataSearchInput, FileDataSearchOutput,
)
from app.services.chat_artifact_reference_service import ChatArtifactReferenceError
from app.services.file_data_service import FileDataError, FileDataService


logger = get_logger(__name__)


async def execute_file_data(ctx: ToolContext, args: dict[str, Any], *, operation: str,
                            input_model: type[BaseModel], output_model: type[BaseModel]) -> ToolResult:
    log = ctx.tool_notes(f"file.data.{operation}")
    try:
        parsed = input_model.model_validate(args)
    except ValidationError:
        return ToolResult.fail("Некорректные параметры операции с файлом", error_code="invalid_arguments", logs=log.entries_dict())
    if not ctx.chat_id or not ctx.user_id:
        return ToolResult.fail("Для работы с файлом нужен контекст пользователя и чата", error_code="file_context_required", logs=log.entries_dict())
    from app.runtime.artifact_visibility import branch_visible_artifacts
    artifact_id = str(parsed.artifact_id)
    visible = branch_visible_artifacts(ctx)
    if visible is not None and artifact_id not in visible:
        return ToolResult.fail("Файл недоступен в этой ветке", error_code="artifact_unavailable", logs=log.entries_dict())
    scope = {"artifact_id": artifact_id, "chat_id": str(ctx.chat_id), "owner_id": str(ctx.user_id),
             "tenant_id": str(ctx.tenant_id) if ctx.tenant_id else None}
    arguments = parsed.model_dump(mode="json", exclude={"artifact_id"})
    log.info("File data operation started", artifact_id=artifact_id, operation=operation)
    try:
        from app.core.db import get_session_factory
        async with get_session_factory()() as session:
            service = FileDataService(session)
            data = await getattr(service, operation)(**scope, **arguments)
            data = output_model.model_validate(data).model_dump(mode="json")
            sources = []
            if operation == "search" and data["hits"]:
                reference = await service.artifacts.get_reference(
                    artifact_id=artifact_id, chat_id=str(ctx.chat_id), owner_id=str(ctx.user_id))
                passport = service.artifacts.manifest(reference)
                sources = [{"source_id": f"{artifact_id}:{data['representation_id']}:{hit['start']}:{hit['end']}",
                    "artifact_id": artifact_id, "artifact": passport, "source_name": reference.display_name,
                    "representation_id": data["representation_id"], "chunk_id": hit["chunk_id"],
                    "start": hit["start"], "end": hit["end"], "text": hit["text"], "score": hit["score"]}
                    for hit in data["hits"]]
            await session.commit()
        log.info("File data operation completed", artifact_id=artifact_id, operation=operation)
        return ToolResult.ok(data=data, delivery="direct", sources=sources, logs=log.entries_dict())
    except FileDataError as exc:
        log.warning("File data is not available", artifact_id=artifact_id, error_code=exc.code)
        return ToolResult.fail(str(exc), error_code=exc.code, logs=log.entries_dict())
    except ChatArtifactReferenceError:
        return ToolResult.fail("Файл недоступен или доступ к источнику отозван", error_code="artifact_unavailable", logs=log.entries_dict())
    except ValueError:
        logger.exception("File data configuration/extraction failed artifact_id=%s", artifact_id)
        return ToolResult.fail("Не удалось подготовить или прочитать документ: проверьте формат, размер и настройки моделей",
                               error_code="file_data_unavailable", logs=log.entries_dict())
    except Exception:
        logger.exception("File data backend failed artifact_id=%s operation=%s", artifact_id, operation)
        return ToolResult.fail("Сервис обработки файла временно недоступен. Поиск не выполнен.",
                               error_code="file_data_backend_unavailable", retryable=True, logs=log.entries_dict())


@register_tool
class FileDataReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "file.data.read"
    tool_group: ClassVar[str] = "file"
    domains: ClassVar[list[str]] = ["system"]
    name: ClassVar[str] = "Read File Data"
    description: ClassVar[str] = "Read a page of versioned canonical document text by artifact_id, offset and limit. Continue with next_offset and representation_id."
    input_schema = FileDataReadInput.model_json_schema()
    output_schema = FileDataReadOutput.model_json_schema()

    @tool_version("1.0.0", input_schema=input_schema, output_schema=output_schema)
    async def v1_0_0(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await execute_file_data(ctx, args, operation="read", input_model=FileDataReadInput, output_model=FileDataReadOutput)


@register_tool
class FileDataPrepareTool(VersionedTool):
    tool_slug: ClassVar[str] = "file.data.prepare"
    tool_group: ClassVar[str] = "file"
    domains: ClassVar[list[str]] = ["system"]
    name: ClassVar[str] = "Prepare File Search"
    description: ClassVar[str] = "Explicitly prepare a private document search index: vector or longmemory (knowledge graph). Does not publish chat files to shared memory."
    input_schema = FileDataPrepareInput.model_json_schema()
    output_schema = FileDataPrepareOutput.model_json_schema()

    @tool_version("1.0.0", input_schema=input_schema, output_schema=output_schema)
    async def v1_0_0(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await execute_file_data(ctx, args, operation="prepare", input_model=FileDataPrepareInput, output_model=FileDataPrepareOutput)


@register_tool
class FileDataSearchTool(VersionedTool):
    tool_slug: ClassVar[str] = "file.data.search"
    tool_group: ClassVar[str] = "file"
    domains: ClassVar[list[str]] = ["system"]
    name: ClassVar[str] = "Search File Data"
    description: ClassVar[str] = "Search within one artifact_id using a prepared vector or LongMemory index. Returns document_not_indexed when the index/scope/chunks are absent or expired; empty hits mean a completed search. Never indexes implicitly."
    input_schema = FileDataSearchInput.model_json_schema()
    output_schema = FileDataSearchOutput.model_json_schema()

    @tool_version("1.0.0", input_schema=input_schema, output_schema=output_schema)
    async def v1_0_0(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return await execute_file_data(ctx, args, operation="search", input_model=FileDataSearchInput, output_model=FileDataSearchOutput)
