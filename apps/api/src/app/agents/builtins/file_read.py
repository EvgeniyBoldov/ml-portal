"""
File Read Tool — reads a file by canonical storage_uri.

Preferred input is an exact S3/MinIO URI in canonical form:
- s3://<bucket>/<key>
"""
from __future__ import annotations

import base64
from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_TEXT_EXTENSIONS = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}
_MAX_READ_BYTES = 2 * 1024 * 1024

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "storage_uri": {
            "type": "string",
            "description": (
                "Canonical storage URI to read, in the form "
                "'s3://<bucket>/<key>'. "
                "Pass the exact storage_uri returned by producer tools such as "
                "collection.document.get, collection.document.list, collection.template.list, "
                "collection.template.fill, or file.generate."
            ),
        },
    },
    "required": ["storage_uri"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string"},
        "storage_uri": {"type": "string"},
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
    Read a file by its canonical storage_uri from chat storage or collection outputs.

    Use this to inspect the contents of a previously uploaded/generated chat file,
    or to read an original file from a document collection (e.g. an Excel template).
    """

    tool_slug: ClassVar[str] = "file.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read File"
    description: ClassVar[str] = (
        "Read a file by its canonical storage_uri (s3://bucket/key). "
        "Returns text content for text files, or base64 for binary files. "
        "Use the exact storage_uri returned by upstream tools."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Read file from S3/MinIO by canonical storage_uri and return its contents",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.adapters.s3_client import s3_manager
        from app.core.db import get_session_factory
        from app.repositories.factory import AsyncRepositoryFactory
        from app.services.file_delivery_service import FileDeliveryService

        log = ctx.tool_logger("file.read")

        storage_uri = str(args.get("storage_uri") or "").strip()
        if not storage_uri:
            log.error("Missing storage_uri")
            return ToolResult.fail("Missing 'storage_uri' argument", logs=log.entries_dict())

        user_id = ctx.user_id
        if not user_id:
            log.error("Missing user_id in tool context")
            return ToolResult.fail(
                "File read requires a user context.",
                logs=log.entries_dict(),
            )

        log.info("Reading file", storage_uri=storage_uri)

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo_factory = AsyncRepositoryFactory(
                    session, tenant_id=ctx.tenant_id, user_id=user_id
                )
                service = FileDeliveryService(session, repo_factory)
                resolved = await service.resolve_storage_uri(storage_uri, owner_id=str(user_id))

                # Load from S3
                payload = await s3_manager.get_object(resolved.bucket, resolved.key)
                if payload is None:
                    log.error("Failed to load file from storage", storage_uri=storage_uri)
                    return ToolResult.fail(
                        f"File '{storage_uri}' exists in storage metadata but could not be loaded from storage.",
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

                ext = ""
                if resolved.file_name and "." in resolved.file_name:
                    ext = resolved.file_name.rsplit(".", 1)[-1].strip().lower()
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
                    file_id=resolved.file_id,
                    storage_uri=storage_uri,
                    file_name=resolved.file_name,
                    size_bytes=size_bytes,
                    encoding=encoding,
                )
                return ToolResult.ok(
                    data={
                        "file_id": resolved.file_id,
                        "storage_uri": storage_uri,
                        "file_name": resolved.file_name,
                        "content_type": resolved.content_type or "application/octet-stream",
                        "size_bytes": size_bytes,
                        "content": content,
                        "encoding": encoding,
                    },
                    message=f"File '{resolved.file_name}' read successfully ({encoding}, {size_bytes} bytes).",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("File read failed: %s", exc, exc_info=True)
            log.error("File read failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to read file: {exc}",
                logs=log.entries_dict(),
            )
