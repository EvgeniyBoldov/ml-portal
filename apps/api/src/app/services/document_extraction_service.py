from __future__ import annotations

import asyncio
import httpx
import mimetypes
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Awaitable, Callable, Optional

from app.core.config import get_settings
from app.services.extractors import BaseExtractor, ExtractResult, ExtractorRegistry


TEXT_EXTENSIONS = {
    "txt", "md", "py", "log", "json", "yaml", "yml", "xml", "html", "htm", "sql", "csv", "tsv"
}
TABLE_EXTENSIONS = {"csv", "tsv", "xlsx"}
DOCLING_EXTENSIONS = {
    "pdf", "docx", "pptx", "xlsx", "html", "htm", "md", "txt", "csv",
    "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp",
}


@dataclass(frozen=True)
class ExtractionRequest:
    payload: bytes
    filename: str
    content_type: Optional[str] = None
    profile: str = "chat_preview"
    max_chars: int = 32_000
    max_bytes: int = 8 * 1024 * 1024
    observer: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None
    fallback_extractor: Optional[BaseExtractor] = None


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
    """Shared Docling-first extraction facade for chat and RAG ingestion."""

    async def extract(self, request: ExtractionRequest) -> ExtractionOutput:
        started_at = asyncio.get_running_loop().time()

        async def observe(stage: str, **payload: Any) -> None:
            if request.observer is not None:
                await request.observer(stage, payload)

        await observe(
            "started", filename=request.filename, profile=request.profile,
            size_bytes=len(request.payload), content_type=request.content_type,
        )
        try:
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
                output = ExtractionOutput(
                    text="", content_kind="binary", parser="unsupported",
                    warnings=["File format is not supported for text extraction"],
                )
                await observe("completed", parser=output.parser, content_kind=output.content_kind,
                              warnings=output.warnings, duration_ms=int((asyncio.get_running_loop().time() - started_at) * 1000))
                return output

            ext = detected.rsplit(".", 1)[-1].lower() if "." in detected else ""
            docling_error: Optional[str] = None
            result: ExtractResult
            if ext in DOCLING_EXTENSIONS:
                try:
                    result = await self._extract_docling(request, detected)
                except Exception as exc:
                    docling_error = f"Docling conversion failed; used local extractor ({type(exc).__name__})"
                    result = await asyncio.to_thread(
                        self._extract_fallback, request, detected
                    )
            else:
                result = await asyncio.to_thread(
                    self._extract_fallback, request, detected
                )
            warnings = list(result.warnings)
            if docling_error:
                warnings.append(docling_error)
            if request.profile == "rag_ingest" and result.meta.get("source_complete") is False:
                raise ValueError("PDF extraction was incomplete; refusing to index a partial document")
            text = result.text or ""
            truncated = False
            if request.profile == "chat_preview" and len(text) > request.max_chars:
                text = text[: request.max_chars]
                truncated = True
                warnings.append(f"Preview truncated to {request.max_chars} characters")

            content_kind = "table" if ext in TABLE_EXTENSIONS else "document"
            if ext in TEXT_EXTENSIONS and ext not in TABLE_EXTENSIONS:
                content_kind = "text"
            table = None
            if content_kind == "table":
                table = {"format": ext, "text_projection": text}

            output = ExtractionOutput(
                text=text, content_kind=content_kind, parser=result.kind,
                meta=dict(result.meta or {}), warnings=warnings, truncated=truncated, table=table,
            )
            await observe(
                "completed", parser=output.parser, content_kind=output.content_kind,
                truncated=output.truncated, warnings=output.warnings,
                output_chars=len(output.text), duration_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            return output
        except Exception as exc:
            await observe(
                "failed", error_code=type(exc).__name__,
                duration_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            raise

    @staticmethod
    async def _extract_docling(request: ExtractionRequest, filename: str) -> ExtractResult:
        settings = get_settings()
        content_type = (
            request.content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        timeout = httpx.Timeout(settings.DOCLING_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.DOCLING_URL.rstrip('/')}/v1/convert/file",
                files={"files": (filename, request.payload, content_type)},
                data={
                    "to_formats": "md",
                    "image_export_mode": "placeholder",
                    "do_ocr": "true",
                    "do_table_structure": "true",
                    "abort_on_error": "true",
                },
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Docling returned an invalid response")
        status = str(payload.get("status") or "").lower()
        document = payload.get("document")
        if status != "success" or not isinstance(document, dict):
            raise ValueError(f"Docling conversion status: {status or 'missing'}")
        text = str(document.get("md_content") or document.get("text_content") or "").strip()
        if not text:
            raise ValueError("Docling returned empty document content")
        warnings: list[str] = []
        meta: dict[str, Any] = {"docling_status": status, "source_complete": True}
        if isinstance(payload.get("processing_time"), (int, float)):
            meta["docling_processing_time"] = payload["processing_time"]
        return ExtractResult(text=text, kind="docling", meta=meta, warnings=warnings)

    @staticmethod
    def _extract_fallback(request: ExtractionRequest, filename: str) -> ExtractResult:
        if request.fallback_extractor is not None:
            return request.fallback_extractor.extract(request.payload, filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in set(ExtractorRegistry.supported_extensions()) | TEXT_EXTENSIONS:
            return ExtractResult(
                text="", kind="unsupported", warnings=[
                    f"Docling is unavailable and no local extractor supports .{extension or 'unknown'}"
                ],
            )
        return ExtractorRegistry.extract(request.payload, filename)

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
        if mime_ext in {
            "doc", "docx", "pdf", "xlsx", "csv", "txt", "pptx", "html", "htm", "md",
            "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp",
        }:
            ext = mime_ext

        if ext in set(ExtractorRegistry.supported_extensions()) | TEXT_EXTENSIONS | DOCLING_EXTENSIONS:
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
