from __future__ import annotations

import asyncio
import mimetypes
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Optional

from app.services.extractors import ExtractResult, ExtractorRegistry


TEXT_EXTENSIONS = {
    "txt", "md", "log", "json", "yaml", "yml", "xml", "html", "htm", "sql", "csv", "tsv"
}
TABLE_EXTENSIONS = {"csv", "tsv", "xlsx"}


@dataclass(frozen=True)
class ExtractionRequest:
    payload: bytes
    filename: str
    content_type: Optional[str] = None
    profile: str = "chat_preview"
    max_chars: int = 32_000
    max_bytes: int = 8 * 1024 * 1024


@dataclass
class ExtractionOutput:
    text: str
    content_kind: str
    parser: str
    meta: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    table: Optional[dict[str, Any]] = None


class DocumentExtractionService:
    """Shared profile-driven facade for tools and RAG ingestion."""

    async def extract(self, request: ExtractionRequest) -> ExtractionOutput:
        if len(request.payload) > request.max_bytes:
            raise ValueError(f"File exceeds extraction limit of {request.max_bytes} bytes")
        if request.profile not in {"chat_preview", "rag_ingest"}:
            raise ValueError(f"Unsupported extraction profile: {request.profile}")

        detected = self.detect_format(
            request.payload,
            filename=request.filename,
            content_type=request.content_type,
        )
        if detected is None:
            return ExtractionOutput(
                text="",
                content_kind="binary",
                parser="unsupported",
                warnings=["File format is not supported for text extraction"],
            )

        result: ExtractResult = await asyncio.to_thread(
            ExtractorRegistry.extract, request.payload, detected
        )
        warnings = list(result.warnings)
        text = result.text or ""
        truncated = False
        if request.profile == "chat_preview" and len(text) > request.max_chars:
            text = text[: request.max_chars]
            truncated = True
            warnings.append(f"Preview truncated to {request.max_chars} characters")

        ext = detected.rsplit(".", 1)[-1].lower() if "." in detected else ""
        content_kind = "table" if ext in TABLE_EXTENSIONS else "document"
        if ext in TEXT_EXTENSIONS and ext not in TABLE_EXTENSIONS:
            content_kind = "text"
        table = None
        if content_kind == "table":
            table = {"format": ext, "text_projection": text}

        return ExtractionOutput(
            text=text,
            content_kind=content_kind,
            parser=result.kind,
            meta=dict(result.meta or {}),
            warnings=warnings,
            truncated=truncated,
            table=table,
        )

    @classmethod
    def detect_format(
        cls,
        payload: bytes,
        *,
        filename: str,
        content_type: Optional[str] = None,
    ) -> Optional[str]:
        """Return a parser-friendly filename after signature/MIME detection."""
        lower_name = str(filename or "file").lower()
        ext = lower_name.rsplit(".", 1)[-1] if "." in lower_name else ""

        if payload.startswith(b"%PDF-"):
            return cls._with_extension(lower_name, "pdf")
        if payload.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return cls._with_extension(lower_name, "doc")
        if zipfile.is_zipfile(BytesIO(payload)):
            try:
                with zipfile.ZipFile(BytesIO(payload)) as archive:
                    names = set(archive.namelist())
                if "word/document.xml" in names:
                    return cls._with_extension(lower_name, "docx")
                if "xl/workbook.xml" in names:
                    return cls._with_extension(lower_name, "xlsx")
            except Exception:
                pass

        normalized_mime = str(content_type or "").split(";", 1)[0].strip().lower()
        mime_ext = mimetypes.guess_extension(normalized_mime or "") or ""
        mime_ext = mime_ext.lstrip(".")
        if mime_ext in {"doc", "docx", "pdf", "xlsx", "csv", "txt"}:
            ext = mime_ext

        if ext in set(ExtractorRegistry.supported_extensions()) | TEXT_EXTENSIONS:
            return cls._with_extension(lower_name, ext)

        # Content sniffing fallback for extensionless UTF-8 text.  NUL bytes
        # deliberately reject the guess so arbitrary binaries are not sent
        # through a text parser.
        if normalized_mime.startswith("text/"):
            return cls._with_extension(lower_name, ext or "txt")
        if not ext and b"\x00" not in payload:
            try:
                payload.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                return cls._with_extension(lower_name, "txt")
        return None

    @staticmethod
    def _with_extension(filename: str, extension: str) -> str:
        stem = filename.rsplit("/", 1)[-1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        return f"{stem}.{extension}"
