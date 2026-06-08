"""
File Delete Tool — deletes a previously uploaded or generated file from chat storage.

Useful when the user asks to clean up files, or when an agent wants to
remove temporary artifacts.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar, Dict

from sqlalchemy import select, and_

from app.adapters.s3_client import s3_manager
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.chat_attachment import ChatAttachment

logger = get_logger(__name__)

_FILE_ID_RE = re.compile(r"^chatatt_([0-9a-fA-F-]{36})$")

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {
            "type": "string",
            "description": "File ID to delete, e.g. 'chatatt_550e8400-e29b-41d4-a716-446655440000'",
        },
    },
    "required": ["file_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "deleted": {"type": "boolean"},
        "file_id": {"type": "string"},
        "file_name": {"type": "string"},
    },
}


@register_tool
class FileDeleteTool(VersionedTool):
    """
    Delete a file from chat storage by file_id.

    Use this when the user asks to remove a file, or when a generated
    temporary file is no longer needed.
    """

    tool_slug: ClassVar[str] = "file.delete"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Delete File"
    description: ClassVar[str] = (
        "Delete a previously uploaded or generated file from chat storage. "
        "Requires the file_id returned by file.list or file.generate."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Delete chat attachment from DB and S3/MinIO",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        import uuid as _uuid

        log = ctx.tool_logger("file.delete")

        file_id = str(args.get("file_id") or "").strip()
        if not file_id:
            log.error("Missing file_id")
            return ToolResult.fail("Missing 'file_id' argument", logs=log.entries_dict())

        match = _FILE_ID_RE.match(file_id)
        if not match:
            log.error("Invalid file_id format", file_id=file_id)
            return ToolResult.fail(
                f"Invalid file_id format '{file_id}'. Expected 'chatatt_<uuid>'.",
                logs=log.entries_dict(),
            )

        attachment_id = match.group(1)
        chat_id = ctx.chat_id
        user_id = ctx.user_id
        if not chat_id or not user_id:
            log.error("Missing chat_id or user_id in tool context")
            return ToolResult.fail(
                "File delete requires a chat context.",
                logs=log.entries_dict(),
            )

        log.info("Deleting file", file_id=file_id, chat_id=str(chat_id))

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                stmt = select(ChatAttachment).where(
                    and_(
                        ChatAttachment.id == _uuid.UUID(attachment_id),
                        ChatAttachment.chat_id == chat_id,
                        ChatAttachment.owner_id == user_id,
                    )
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if not row:
                    log.error("File not found", file_id=file_id, chat_id=str(chat_id))
                    return ToolResult.fail(
                        f"File '{file_id}' not found in this chat or access denied.",
                        logs=log.entries_dict(),
                    )

                file_name = row.file_name
                bucket = row.storage_bucket
                key = row.storage_key

                # Delete from S3 first
                deleted_s3 = await s3_manager.delete_object(bucket, key)
                if not deleted_s3:
                    log.warning("S3 delete returned False", bucket=bucket, key=key, file_id=file_id)
                    # Continue to delete DB row anyway — orphaned object is less bad than stale reference

                await session.delete(row)
                await session.flush()

                log.info("File deleted", file_id=file_id, file_name=file_name)
                return ToolResult.ok(
                    data={"deleted": True, "file_id": file_id, "file_name": file_name},
                    message=f"File '{file_name}' ({file_id}) deleted successfully.",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("File delete failed: %s", exc, exc_info=True)
            log.error("File delete failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to delete file: {exc}",
                logs=log.entries_dict(),
            )
