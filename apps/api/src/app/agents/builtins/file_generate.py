"""
File Generate Tool — saves a generated file and returns canonical artifact info.

The agent (not the orchestrator) owns content creation. This tool is a thin
write-through to ChatAttachmentService: it persists the agent-generated body
to S3 / MinIO and returns a stable download URL.

Supported formats: csv, json, txt, md.
Excel support is TODO — it requires binary generation (e.g. openpyxl/xlsxwriter).
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_FORMATS = {"csv", "json", "txt", "md"}
_CONTENT_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "txt": "text/plain",
    "md": "text/markdown",
}

# Limit to prevent accidental abuse (2 MB text ≈ huge)
_MAX_FILE_BYTES = 2 * 1024 * 1024

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "File name including extension, e.g. 'report.csv'",
        },
        "content": {
            "type": "string",
            "description": "Full file body as a UTF-8 string. The agent must format it correctly (e.g. CSV rows, JSON object).",
        },
        "format": {
            "type": "string",
            "description": "File format: csv, json, txt, or md.",
            "enum": list(_SUPPORTED_FORMATS),
        },
    },
    "required": ["filename", "content", "format"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string", "description": "Stable file identifier (e.g. chatatt_<uuid>)"},
        "storage_uri": {"type": "string", "description": "Canonical storage URI in the form s3://bucket/key"},
        "download_url": {"type": "string", "description": "Absolute download endpoint for the file"},
        "file_name": {"type": "string"},
        "content_type": {"type": "string"},
        "size_bytes": {"type": "integer"},
    },
}


@register_tool
class FileGenerateTool(VersionedTool):
    """
    Persist a generated file.

    Use this when the user explicitly asks for a downloadable artifact
    (report, export, plan, etc.). The agent must produce the full content
    string; this tool saves it and returns a stable download link.
    """

    tool_slug: ClassVar[str] = "file.generate"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Generate File"
    description: ClassVar[str] = (
        "Save a generated file (csv, json, txt, md) to chat storage and return its canonical storage_uri and download link. "
        "The agent must provide the fully formatted file body."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Save generated file body to S3/MinIO and return download metadata",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.core.db import get_session_factory
        from app.services.chat_attachment_service import ChatAttachmentService

        log = ctx.tool_logger("file.generate")

        filename = str(args.get("filename") or "").strip()
        content = str(args.get("content") or "")
        fmt = str(args.get("format") or "").strip().lower()

        if not filename:
            log.error("Missing filename")
            return ToolResult.fail("Missing 'filename' argument", logs=log.entries_dict())

        if not content:
            log.error("Empty content")
            return ToolResult.fail("Missing 'content' argument", logs=log.entries_dict())

        if fmt not in _SUPPORTED_FORMATS:
            log.error("Unsupported format", requested=fmt, supported=list(_SUPPORTED_FORMATS))
            return ToolResult.fail(
                f"Unsupported format '{fmt}'. Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}. "
                "Excel (.xlsx) support is planned but not yet implemented.",
                logs=log.entries_dict(),
            )

        # Derive content_type from format or filename
        content_type = _CONTENT_TYPES.get(fmt)
        if not content_type and "." in filename:
            ext = filename.rsplit(".", 1)[-1].strip().lower()
            content_type = _CONTENT_TYPES.get(ext)

        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            log.error(
                "File too large",
                size_bytes=len(encoded),
                max_bytes=_MAX_FILE_BYTES,
            )
            return ToolResult.fail(
                f"File content exceeds limit of {_MAX_FILE_BYTES} bytes. "
                "Consider splitting into multiple smaller files or reducing data.",
                logs=log.entries_dict(),
            )

        user_id = ctx.user_id
        chat_id = ctx.chat_id

        log.info(
            "Generating file",
            filename=filename,
            format=fmt,
            size_bytes=len(encoded),
            chat_id=str(chat_id) if chat_id else None,
        )

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = ChatAttachmentService(session)
                attachment = await service.create_generated_attachment(
                    chat_id=str(chat_id) if chat_id else None,
                    owner_id=str(user_id),
                    filename=filename,
                    content=encoded,
                    content_type=content_type,
                )
                await session.commit()
                log.info(
                    "File saved",
                    attachment_id=attachment.get("id"),
                    file_id=attachment.get("file_id"),
                    size_bytes=attachment.get("size_bytes"),
                )
                return ToolResult.ok(
                    data={
                        "file_id": attachment.get("file_id"),
                        "storage_uri": attachment.get("storage_uri"),
                        "download_url": f"/api/v1/files/{attachment.get('file_id')}/download",
                        "file_name": attachment.get("file_name"),
                        "content_type": content_type,
                        "size_bytes": attachment.get("size_bytes"),
                    },
                    message=f"File '{filename}' generated successfully.",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("File generation failed: %s", exc, exc_info=True)
            log.error("File generation failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to save generated file: {exc}",
                logs=log.entries_dict(),
            )
