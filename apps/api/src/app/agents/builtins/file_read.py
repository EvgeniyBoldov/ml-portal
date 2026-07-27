"""Read a bounded representation of a chat-scoped artifact."""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_TEXT_EXTENSIONS = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}
_MAX_READ_BYTES = 2 * 1024 * 1024

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {"artifact_id": {"type": "string", "description": "Chat artifact reference UUID"}},
    "required": ["artifact_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "artifact_id": {"type": "string"},
        "file_name": {"type": "string"},
        "content_type": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "representation": {"type": "string", "enum": ["text", "document", "table", "binary"]},
        "content": {"type": "string", "description": "Bounded extracted content"},
        "truncated": {"type": "boolean"},
        "parser": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}


@register_tool
class FileReadTool(VersionedTool):
    """
    Read a file by a chat-scoped artifact reference from chat or collection outputs.

    Use this to inspect the contents of a previously uploaded/generated chat file,
    or to read an original file from a document collection (e.g. an Excel template).
    """

    tool_slug: ClassVar[str] = "file.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read File"
    description: ClassVar[str] = (
        "Read a bounded text, document, or table representation of a referenced artifact."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Resolve a chat artifact reference, validate access, and extract a bounded preview",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.adapters.s3_client import s3_manager
        from app.core.db import get_session_factory
        from app.services.chat_artifact_reference_service import (
            ChatArtifactReferenceError,
            ChatArtifactReferenceNotFound,
            ChatArtifactReferenceService,
        )
        from app.services.document_extraction_service import DocumentExtractionService, ExtractionRequest

        log = ctx.tool_notes("file.read")

        artifact_id = str(args.get("artifact_id") or "").strip()
        if not artifact_id:
            log.error("Missing artifact_id")
            return ToolResult.fail("Missing 'artifact_id' argument", logs=log.entries_dict())

        user_id = ctx.user_id
        if not user_id:
            log.error("Missing user_id in tool context")
            return ToolResult.fail(
                "File read requires a user context.",
                logs=log.entries_dict(),
            )

        chat_id = ctx.chat_id
        if not chat_id:
            return ToolResult.fail("File read requires a chat context.", logs=log.entries_dict())
        log.info("Reading artifact", artifact_id=artifact_id)

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = ChatArtifactReferenceService(session)
                if artifact_id.startswith("chatatt_"):
                    try:
                        attachment_id = uuid.UUID(artifact_id.removeprefix("chatatt_"))
                        reference = await service.get_reference_for_target(
                            target_kind="chat_attachment",
                            target_id=attachment_id,
                            chat_id=chat_id,
                            owner_id=user_id,
                        )
                        artifact_id = str(reference.id)
                    except (ValueError, ChatArtifactReferenceNotFound):
                        return ToolResult.fail("Invalid artifact_id", logs=log.entries_dict())
                resolved = await service.resolve(
                    artifact_id=artifact_id,
                    chat_id=chat_id,
                    owner_id=user_id,
                    tenant_id=ctx.tenant_id,
                )
                payload = await s3_manager.get_object(resolved.bucket, resolved.key)
                if payload is None:
                    log.error("Failed to load artifact from storage", artifact_id=artifact_id)
                    return ToolResult.fail(
                        "Artifact exists in metadata but could not be loaded from storage.",
                        logs=log.entries_dict(),
                    )
                size_bytes = len(payload)
                call_id = str(ctx.extra.get("runtime_active_tool_call_id") or artifact_id)
                async def observe_extraction(stage: str, payload: dict) -> None:
                    sink = ctx.extra.get("runtime_event_logger")
                    if sink is None:
                        return
                    from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
                    event_type = {
                        "started": RuntimeEventType.EXTRACTION_STARTED,
                        "completed": RuntimeEventType.EXTRACTION_COMPLETED,
                        "failed": RuntimeEventType.EXTRACTION_FAILED,
                    }[stage]
                    await sink.emit(RuntimeEvent(event_type, {
                        "entity_type": "extraction",
                        "entity_id": f"{call_id}:extraction",
                        "parent_entity_type": "tool_call",
                        "parent_entity_id": call_id,
                        "artifact_id": artifact_id,
                        **payload,
                    }), phase=OrchestrationPhase.AGENT)

                extraction = await DocumentExtractionService().extract(
                    ExtractionRequest(
                        payload=payload,
                        filename=resolved.file_name,
                        content_type=resolved.content_type,
                        profile="chat_preview",
                        max_bytes=_MAX_READ_BYTES,
                        observer=observe_extraction,
                    )
                )

                log.info(
                    "File read OK",
                    artifact_id=artifact_id,
                    file_name=resolved.file_name,
                    size_bytes=size_bytes,
                    representation=extraction.content_kind,
                )
                return ToolResult.ok(
                    data={
                        "artifact_id": artifact_id,
                        "file_name": resolved.file_name,
                        "content_type": resolved.content_type or "application/octet-stream",
                        "size_bytes": size_bytes,
                        "representation": extraction.content_kind,
                        "content": extraction.text,
                        "truncated": extraction.truncated,
                        "parser": extraction.parser,
                        "warnings": extraction.warnings,
                    },
                    message=f"File '{resolved.file_name}' read successfully.",
                    logs=log.entries_dict(),
                )
        except ChatArtifactReferenceError as exc:
            log.error("Artifact access denied or missing", error=str(exc))
            return ToolResult.fail(str(exc), logs=log.entries_dict())
        except Exception as exc:
            logger.error("File read failed: %s", exc, exc_info=True)
            log.error("File read failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to read file: {exc}",
                logs=log.entries_dict(),
            )
