from __future__ import annotations

import csv
import io
import json
import re
from pathlib import PurePosixPath
from typing import Dict

from app.services.file_formats.types import EncodedFile, FileCodec, FileFormat


class _TextCodec:
    def __init__(self, file_format: FileFormat) -> None:
        self.format = file_format

    def encode(self, content: str, filename: str) -> EncodedFile:
        return EncodedFile(
            content=content.encode("utf-8"),
            filename=_normalize_filename(filename, self.format.extension),
            format=self.format,
        )


class _JsonCodec(_TextCodec):
    def encode(self, content: str, filename: str) -> EncodedFile:
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON content: {exc.msg}") from exc
        return super().encode(content, filename)


class _CsvCodec(_TextCodec):
    def encode(self, content: str, filename: str) -> EncodedFile:
        if not content.strip():
            raise ValueError("CSV content must not be empty")
        try:
            list(csv.reader(io.StringIO(content)))
        except csv.Error as exc:
            raise ValueError(f"Invalid CSV content: {exc}") from exc
        return super().encode(content, filename)


class _DocxCodec:
    format = FileFormat(
        name="docx",
        extension="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    def encode(self, content: str, filename: str) -> EncodedFile:
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise RuntimeError("DOCX generation requires python-docx") from exc

        document = Document()
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
        if not blocks and normalized:
            blocks = [normalized]
        for block in blocks:
            lines = [line.rstrip() for line in block.splitlines() if line.strip()]
            if lines:
                document.add_paragraph("\n".join(lines))
        output = io.BytesIO()
        document.save(output)
        return EncodedFile(
            content=output.getvalue(),
            filename=_normalize_filename(filename, self.format.extension),
            format=self.format,
        )


class FileCodecRegistry:
    """Canonical registry for formats accepted by file generation."""

    _codecs: Dict[str, FileCodec] = {
        "txt": _TextCodec(FileFormat("txt", "txt", "text/plain")),
        "py": _TextCodec(FileFormat("py", "py", "text/x-python")),
        "md": _TextCodec(FileFormat("md", "md", "text/markdown")),
        "json": _JsonCodec(FileFormat("json", "json", "application/json")),
        "csv": _CsvCodec(FileFormat("csv", "csv", "text/csv")),
        "docx": _DocxCodec(),
    }

    @classmethod
    def get(cls, format_name: str) -> FileCodec:
        normalized = str(format_name or "").strip().lower().lstrip(".")
        codec = cls._codecs.get(normalized)
        if codec is None:
            raise ValueError(f"Unsupported file format: {format_name}")
        return codec

    @classmethod
    def supported_formats(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._codecs))

    @classmethod
    def format_for_filename(cls, filename: str) -> FileFormat | None:
        extension = PurePosixPath(str(filename or "").strip()).suffix.lower().lstrip(".")
        if not extension:
            return None
        try:
            return cls.get(extension).format
        except ValueError:
            return None


def _normalize_filename(filename: str, extension: str) -> str:
    raw = PurePosixPath(str(filename or "file").strip()).name or "file"
    raw = re.sub(r"[\\/:*?\"<>|]+", "_", raw).strip(" .") or "file"
    current = PurePosixPath(raw).suffix.lower().lstrip(".")
    if current != extension:
        raw = f"{PurePosixPath(raw).stem}.{extension}"
    return raw
