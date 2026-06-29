"""
collection.template.fill — Fill a template with values and return a generated file.

Supports Excel, Word, and plain text templates via placeholder substitution.
The filled result is stored as a chat attachment and its canonical storage_uri is returned.
"""
from __future__ import annotations

import io
import re
from typing import Any, ClassVar, Dict, List, Optional

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.collection import CollectionType
from app.services.chat_attachment_service import ChatAttachmentService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.template_contract import TemplateContract
from app.services.collection.template_fill_engine import TemplateFillEngine
from app.services.collection.template_layout_parser import _parse_placeholder_expr
from app.services.collection_service import CollectionService
from app.services.file_delivery_service import FileDeliveryService
from app.adapters.s3_client import s3_manager

logger = get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+)\}\}")

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_id": {
            "type": "string",
            "description": "UUID or slug of the template collection",
        },
        "row_id": {
            "type": "string",
            "description": "UUID of the template row",
        },
        "values": {
            "type": "object",
            "description": "Key-value map of placeholders to fill",
        },
    },
    "required": ["collection_id", "row_id", "values"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "file_id": {"type": "string"},
        "storage_uri": {"type": "string"},
        "download_url": {"type": "string"},
        "filename": {"type": "string"},
        "size_bytes": {"type": "integer"},
        "format": {"type": "string"},
        "filled_placeholders": {"type": "integer"},
        "missing_placeholders": {"type": "array", "items": {"type": "string"}},
    },
}


def _fill_text(content: bytes, values: Dict[str, str]) -> bytes:
    text = content.decode("utf-8")
    text, _ = _substitute_placeholders(text, values)
    return text.encode("utf-8")


def _fill_excel(content: bytes, values: Dict[str, str]) -> bytes:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is not installed; cannot fill Excel templates")

    wb = openpyxl.load_workbook(io.BytesIO(content))
    filled = set()
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    new_val, keys = _substitute_placeholders(cell.value, values)
                    if new_val != cell.value:
                        cell.value = new_val
                        filled.update(keys)
    out = io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def _fill_word(content: bytes, values: Dict[str, str]) -> bytes:
    try:
        import docx
    except ImportError:
        raise RuntimeError("python-docx is not installed; cannot fill Word templates")

    doc = docx.Document(io.BytesIO(content))
    filled = set()

    for para in doc.paragraphs:
        if para.text:
            new_text, keys = _substitute_placeholders(para.text, values)
            if new_text != para.text:
                para.clear()
                para.add_run(new_text)
                filled.update(keys)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    new_text, keys = _substitute_placeholders(cell.text, values)
                    if new_text != cell.text:
                        cell.paragraphs[0].clear()
                        cell.paragraphs[0].add_run(new_text)
                        filled.update(keys)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _substitute_placeholders(text: str, values: Dict[str, str]) -> tuple[str, set[str]]:
    keys_used = set()

    def replacer(match: Any) -> str:
        parsed = _parse_placeholder_expr(match.group(1))
        if not parsed:
            return match.group(0)
        key, _, _ = parsed
        if key in values:
            keys_used.add(key)
            return str(values[key])
        return match.group(0)

    result = _PLACEHOLDER_RE.sub(replacer, text)
    return result, keys_used


def _flatten_values(values: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_values(value, path))
        else:
            flattened[path] = value
    return flattened


@register_tool
class TemplateFillTool(VersionedTool):
    """Fill a template with values and return a generated file."""

    tool_slug: ClassVar[str] = "collection.template.fill"
    domains: ClassVar[list] = ["collection.template"]
    name: ClassVar[str] = "Fill Template"
    description: ClassVar[str] = (
        "Fill a template (Excel, Word, or text) with provided values. "
        "Placeholders like {{field_name}} are replaced. "
        "Returns a generated file storage_uri that can be passed to file.read or file.analyze, plus download info."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Fill template and return file",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("collection.template.fill")

        collection_id = str(args.get("collection_id") or "").strip()
        row_id = str(args.get("row_id") or "").strip()
        values = args.get("values") or {}

        if not collection_id or not row_id:
            log.error("Missing collection_id or row_id")
            return ToolResult.fail(
                "Missing 'collection_id' or 'row_id' argument",
                logs=log.entries_dict(),
            )
        if not isinstance(values, dict):
            log.error("Invalid values type", type=type(values).__name__)
            return ToolResult.fail("'values' must be an object/dict", logs=log.entries_dict())

        try:
            import uuid
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                try:
                    cid = uuid.UUID(collection_id)
                    collection = await service.get_by_id(cid)
                except ValueError:
                    collection = await service.get_by_slug(collection_id)

                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_id}' not found",
                        logs=log.entries_dict(),
                    )
                if collection.collection_type != CollectionType.TEMPLATE.value:
                    return ToolResult.fail(
                        f"Collection '{collection_id}' is not a template collection",
                        logs=log.entries_dict(),
                    )

                rid = uuid.UUID(row_id)
                row_service = CollectionRowService(session)
                row = await row_service.get_row_by_id(collection, rid)
                if not row:
                    return ToolResult.fail(
                        f"Template row '{row_id}' not found",
                        logs=log.entries_dict(),
                    )

                file_meta = row.get("file") or {}
                s3_key = file_meta.get("s3_key")
                bucket = file_meta.get("bucket")
                filename = file_meta.get("filename") or "template"
                if not s3_key or not bucket:
                    return ToolResult.fail(
                        "Template file metadata is incomplete (missing s3_key or bucket)",
                        logs=log.entries_dict(),
                    )

                # Download template from S3
                content = await s3_manager.get_object(bucket, s3_key)
                if content is None:
                    return ToolResult.fail(
                        f"Failed to load template file from storage: {bucket}/{s3_key}",
                        logs=log.entries_dict(),
                    )

                # Determine format for response
                ext = ""
                if "." in filename:
                    ext = filename.rsplit(".", 1)[-1].strip().lower()
                if ext in {"xlsx", "xls", "xlsm"}:
                    fmt = "excel"
                elif ext in {"docx", "doc"}:
                    fmt = "word"
                else:
                    fmt = "text"

                # Load contract
                raw_schema = row.get("template_schema") or {}
                contract = TemplateContract.from_jsonb(raw_schema)

                if contract.fields:
                    # Contract-aware filling with validation (preferred path)
                    engine = TemplateFillEngine(contract)
                    result = engine.fill(content, values, filename)
                    if not result.success:
                        return ToolResult.fail(
                            f"Failed to fill template: {result.error}",
                            logs=log.entries_dict(),
                        )
                    filled_bytes = result.content
                    filled_keys = set(result.filled_scalars + result.filled_tables)
                    missing = list(set(result.missing_scalars + result.missing_tables))
                else:
                    # Backward-compat fallback: template has no analyzed schema yet.
                    # Perform naive {{key}} substitution from provided values.
                    log.warning("No contract schema; using naive placeholder substitution")
                    str_values = {
                        k: str(v)
                        for k, v in _flatten_values(values).items()
                        if not isinstance(v, (dict, list))
                    }
                    if fmt == "excel":
                        filled_bytes = _fill_excel(content, str_values)
                    elif fmt == "word":
                        filled_bytes = _fill_word(content, str_values)
                    else:
                        filled_bytes = _fill_text(content, str_values)
                    filled_keys = set(str_values.keys())
                    missing = []

                # Store generated attachment
                chat_id = str(ctx.chat_id or "")
                owner_id = str(ctx.user_id or "")
                if not chat_id or not owner_id:
                    return ToolResult.fail(
                        "Tool context missing chat_id or user_id; cannot store generated file",
                        logs=log.entries_dict(),
                    )

                att_service = ChatAttachmentService(session)
                safe_filename = f"filled_{filename}"
                attachment = await att_service.create_generated_attachment(
                    chat_id=chat_id,
                    owner_id=owner_id,
                    filename=safe_filename,
                    content=filled_bytes,
                    content_type=file_meta.get("content_type") or "application/octet-stream",
                )
                await session.commit()

                file_id = FileDeliveryService.make_chat_attachment_file_id(str(attachment["id"]))

                return ToolResult.ok(
                    data={
                        "file_id": file_id,
                        "storage_uri": attachment.get("storage_uri"),
                        "download_url": f"/api/v1/files/{file_id}/download",
                        "filename": safe_filename,
                        "size_bytes": len(filled_bytes),
                        "format": fmt,
                        "filled_placeholders": len(filled_keys),
                        "missing_placeholders": missing,
                    },
                    message=(
                        f"Filled template '{filename}' ({fmt}, {len(filled_keys)} placeholders). "
                        f"Generated file_id: {file_id}."
                    ),
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("collection.template.fill failed: %s", exc, exc_info=True)
            log.error("collection.template.fill failed", error=str(exc))
            return ToolResult.fail(f"Failed to fill template: {exc}", logs=log.entries_dict())
