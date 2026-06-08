"""
File Read Tool — reads a previously uploaded or generated file from chat storage.

The agent can read files that were either uploaded by the user or generated
by the agent itself via file.generate. Returns file content as text for
supported text formats, or base64 for binary files.
"""
from __future__ import annotations

import base64
import re
from typing import Any, ClassVar, Dict, Optional

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_TEXT_EXTENSIONS = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}
_MAX_READ_BYTES = 2 * 1024 * 1024

_FILE_ID_RE = re.compile(r"^chatatt_([0-9a-fA-F-]{36})$")

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {
            "type": "string",
            "description": (
                "Chat attachment ID to read, e.g. 'chatatt_550e8400-e29b-41d4-a716-446655440000'. "
                "Use only IDs returned by file.generate or file.list, or user-uploaded chat attachments. "
                "Do not pass document/source IDs from RAG search results."
            ),
        },
    },
    "required": ["file_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string"},
        "file_name": {"type": "string"},
        "content_type": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "content": {"type": "string", "description": "Text content or base64-encoded binary"},
        "encoding": {"type": "string", "description": "'text' or 'base64'"},
    },
}


@register_tool
class FileReadTool(VersionedTool):
    """
    Read a file from chat storage by file_id.

    Use this when the user refers to a previously uploaded/generated file,
    or when you need to inspect the contents of a file you created earlier.
    """

    tool_slug: ClassVar[str] = "file.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read File"
    description: ClassVar[str] = (
        "Read a previously uploaded or generated file from chat storage. "
        "Accepts only chat attachment IDs in format chatatt_<uuid>. "
        "Returns text content for text files, or base64 for binary files."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Read file from S3/MinIO and return its contents",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        import uuid

        from sqlalchemy import select, and_

        from app.adapters.s3_client import s3_manager
        from app.core.db import get_session_factory
        from app.models.chat_attachment import ChatAttachment

        log = ctx.tool_logger("file.read")

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
                "File read requires a chat context. Cannot read outside of a chat.",
                logs=log.entries_dict(),
            )

        log.info("Reading file", file_id=file_id, chat_id=str(chat_id))

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                stmt = select(ChatAttachment).where(
                    and_(
                        ChatAttachment.id == uuid.UUID(attachment_id),
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

                # Load from S3
                payload = await s3_manager.get_object(row.storage_bucket, row.storage_key)
                if payload is None:
                    log.error("Failed to load file from storage", file_id=file_id)
                    return ToolResult.fail(
                        f"File '{file_id}' exists in database but could not be loaded from storage.",
                        logs=log.entries_dict(),
                    )

                size_bytes = len(payload)
                if size_bytes > _MAX_READ_BYTES:
                    log.error(
                        "File too large",
                        size_bytes=size_bytes,
                        max_bytes=_MAX_READ_BYTES,
                    )
                    return ToolResult.fail(
                        f"File size ({size_bytes} bytes) exceeds read limit of {_MAX_READ_BYTES} bytes. "
                        "Consider asking the user to provide a smaller file.",
                        logs=log.entries_dict(),
                    )

                ext = (row.file_ext or "").strip().lower()
                is_text = ext in _TEXT_EXTENSIONS

                if is_text:
                    try:
                        content = payload.decode("utf-8")
                        encoding = "text"
                    except UnicodeDecodeError:
                        content = base64.b64encode(payload).decode("ascii")
                        encoding = "base64"
                        is_text = False
                else:
                    content = base64.b64encode(payload).decode("ascii")
                    encoding = "base64"

                log.info(
                    "File read OK",
                    file_id=file_id,
                    file_name=row.file_name,
                    size_bytes=size_bytes,
                    encoding=encoding,
                )
                return ToolResult.ok(
                    data={
                        "file_id": file_id,
                        "file_name": row.file_name,
                        "content_type": row.content_type or "application/octet-stream",
                        "size_bytes": size_bytes,
                        "content": content,
                        "encoding": encoding,
                    },
                    message=f"File '{row.file_name}' read successfully ({encoding}, {size_bytes} bytes).",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("File read failed: %s", exc, exc_info=True)
            log.error("File read failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to read file: {exc}",
                logs=log.entries_dict(),
            )
