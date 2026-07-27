"""
File Generate Tool — saves a generated file and returns canonical artifact info.

The agent (not the orchestrator) owns content creation. This tool delegates
serialization and canonical artifact persistence to shared services.

Supported formats: csv, json, txt, md, docx.
Excel support is TODO — it requires binary generation (e.g. openpyxl/xlsxwriter).
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger
from app.services.file_formats import FileCodecRegistry

logger = get_logger(__name__)

_SUPPORTED_FORMATS = set(FileCodecRegistry.supported_formats())

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
            "description": "File format: csv, json, txt, md, or docx.",
            "enum": sorted(_SUPPORTED_FORMATS),
        },
    },
    "required": ["filename", "content", "format"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "artifact_id": {"type": "string", "description": "Chat-scoped artifact reference UUID"},
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
        "Create a new downloadable file and register it as a chat artifact."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Save generated file body to S3/MinIO and return download metadata",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.core.db import get_session_factory
        from app.services.file_generation_service import FileGenerationService

        log = ctx.tool_notes("file.generate")

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
                "Excel (.xlsx) and legacy Word (.doc) support are not implemented here.",
                logs=log.entries_dict(),
            )

        output_filename = filename

        user_id = ctx.user_id
        chat_id = ctx.chat_id
        if not user_id:
            return ToolResult.fail(
                "File generation requires a user context.",
                logs=log.entries_dict(),
            )
        if not chat_id:
            return ToolResult.fail(
                "File generation requires a chat context.",
                logs=log.entries_dict(),
            )

        log.info(
            "Generating file",
            filename=output_filename,
            format=fmt,
            chat_id=str(chat_id) if chat_id else None,
        )

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                artifact = await FileGenerationService(session).generate(
                    chat_id=str(chat_id),
                    owner_id=str(user_id),
                    filename=output_filename,
                    content=content,
                    format_name=fmt,
                )
                await session.commit()
                log.info(
                    "File saved",
                    artifact_id=artifact.artifact_id,
                    size_bytes=artifact.size_bytes,
                )
                return ToolResult.ok(
                    data={
                        "artifact_id": artifact.artifact_id,
                        "file_name": artifact.file_name,
                        "content_type": artifact.content_type,
                        "size_bytes": artifact.size_bytes,
                    },
                    message=f"File '{output_filename}' generated successfully.",
                    logs=log.entries_dict(),
                )
        except ValueError as exc:
            log.error("Invalid generated file content", error=str(exc))
            return ToolResult.fail(f"Invalid generated file: {exc}", logs=log.entries_dict())
        except Exception as exc:
            logger.error("File generation failed: %s", exc, exc_info=True)
            log.error("File generation failed", error=str(exc))
            return ToolResult.fail(
                f"Failed to save generated file: {exc}",
                logs=log.entries_dict(),
            )
