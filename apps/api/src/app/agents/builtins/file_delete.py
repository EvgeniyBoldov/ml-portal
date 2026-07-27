"""
File Delete Tool — deletes a previously uploaded or generated file from chat storage.

Useful when the user asks to clean up files, or when an agent wants to
remove temporary artifacts.
"""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.services.chat_artifact_reference_service import (
    ChatArtifactReferenceError,
    ChatArtifactReferenceNotFound,
    ChatArtifactReferenceService,
)

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "artifact_id": {
            "type": "string",
            "description": "Chat artifact reference UUID to delete",
        },
    },
    "required": ["artifact_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "deleted": {"type": "boolean"},
        "artifact_id": {"type": "string"},
        "file_name": {"type": "string"},
    },
}


@register_tool
class FileDeleteTool(VersionedTool):
    """
    Delete a chat artifact reference; owned chat storage is removed with it.

    Use this when the user asks to remove a file, or when a generated
    temporary file is no longer needed.
    """

    tool_slug: ClassVar[str] = "file.delete"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Delete File"
    description: ClassVar[str] = (
        "Delete a file reference from the current chat. Chat attachments are deleted from storage too."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Delete chat attachment from DB and S3/MinIO",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes("file.delete")

        artifact_id = str(args.get("artifact_id") or "").strip()
        if not artifact_id:
            log.error("Missing artifact_id")
            return ToolResult.fail("Missing 'artifact_id' argument", logs=log.entries_dict())
        chat_id = ctx.chat_id
        user_id = ctx.user_id
        if not chat_id or not user_id:
            log.error("Missing chat_id or user_id in tool context")
            return ToolResult.fail(
                "File delete requires a chat context.",
                logs=log.entries_dict(),
            )

        log.info("Deleting artifact reference", artifact_id=artifact_id, chat_id=str(chat_id))

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = ChatArtifactReferenceService(session)
                if artifact_id.startswith("chatatt_"):
                    try:
                        reference = await service.get_reference_for_target(
                            target_kind="chat_attachment",
                            target_id=uuid.UUID(artifact_id.removeprefix("chatatt_")),
                            chat_id=chat_id,
                            owner_id=user_id,
                        )
                        artifact_id = str(reference.id)
                    except (ValueError, ChatArtifactReferenceNotFound):
                        return ToolResult.fail("Invalid artifact_id", logs=log.entries_dict())
                deleted = await service.delete_reference(
                    artifact_id=artifact_id,
                    chat_id=chat_id,
                    owner_id=user_id,
                    tenant_id=ctx.tenant_id,
                )
                await session.commit()
                log.info("Artifact deleted", artifact_id=artifact_id)
                return ToolResult.ok(
                    data=deleted,
                    message=f"File '{deleted.get('file_name')}' deleted successfully.",
                    logs=log.entries_dict(),
                )
        except ChatArtifactReferenceError as exc:
            log.error("Artifact delete failed", error=str(exc))
            return ToolResult.fail(str(exc), logs=log.entries_dict())
        except Exception as exc:
            logger.error("File delete failed: %s", exc, exc_info=True)
            log.error("File delete failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to delete file: {exc}",
                logs=log.entries_dict(),
            )
