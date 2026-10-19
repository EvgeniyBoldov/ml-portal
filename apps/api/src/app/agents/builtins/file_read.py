"""Read a bounded representation of a chat-scoped artifact."""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {"artifact_id": {"type": "string", "description": "Chat artifact reference UUID"}},
    "required": ["artifact_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "artifact_id": {"type": "string"},
        "artifact": {"type": "object", "description": "Normalized, content-free artifact passport"},
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
        from app.core.db import get_session_factory
        from app.services.chat_artifact_reference_service import (
            ChatArtifactReferenceError,
            ChatArtifactReferenceNotFound,
            ChatArtifactReferenceService,
        )

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
                from app.runtime.artifact_visibility import branch_visible_artifacts
                visible = branch_visible_artifacts(ctx)
                if visible is not None and artifact_id not in visible:
                    return ToolResult.fail("Artifact is unavailable in this branch", logs=log.entries_dict())
                from app.runtime.events import RuntimeEvent, RuntimeEventType, OrchestrationPhase
                call_id = str(ctx.extra.get("runtime_active_tool_call_id") or artifact_id)
                sink = ctx.extra.get("runtime_event_logger")
                actor = ctx.extra.get("runtime_read_actor", "agent")
                phase = {"turn_preflight": OrchestrationPhase.PREFLIGHT,
                         "planner": OrchestrationPhase.PLANNER}.get(actor, OrchestrationPhase.AGENT)

                async def observe(stage: str, payload: dict) -> None:
                    if sink is not None:
                        event_type = {"started": RuntimeEventType.EXTRACTION_STARTED,
                            "completed": RuntimeEventType.EXTRACTION_COMPLETED,
                            "failed": RuntimeEventType.EXTRACTION_FAILED}[stage]
                        await sink.emit(RuntimeEvent(event_type, {"entity_type": "extraction",
                            "entity_id": f"{call_id}:extraction", "parent_entity_type": "tool_call",
                            "parent_entity_id": call_id, "artifact_id": artifact_id, **payload}), phase=phase)

                from app.services.artifact_representation_service import ArtifactRepresentationService
                data = await ArtifactRepresentationService(session).read(
                    artifact_id=artifact_id, chat_id=str(chat_id), owner_id=str(user_id),
                    tenant_id=str(ctx.tenant_id) if ctx.tenant_id else None, observer=observe)
                reference = await service.get_reference(
                    artifact_id=artifact_id, chat_id=chat_id, owner_id=user_id)
                data["artifact"] = service.manifest(reference)
                await session.commit()
                if sink is not None:
                    await sink.emit(RuntimeEvent.status("file_representation_used", artifact_id=artifact_id,
                        representation_id=data["representation_id"], reused=data["reused"],
                        truncated=data["truncated"], parent_entity_type="tool_call", parent_entity_id=call_id), phase=phase)
                return ToolResult.ok(
                    data=data, delivery="direct",
                    message=f"File '{data['file_name']}' read successfully.",
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
