from __future__ import annotations

from typing import Optional

from app.services.extractors.base import ExtractResult
from app.services.extractors.doc import DocExtractor
from app.services.extractors.docx import DocxExtractor
from app.services.extractors.text import _decode_best_effort

_TEXT_EXTENSIONS = {"txt", "md", "csv", "tsv", "json", "yaml", "yml", "log", "sql", "xml", "html"}


def _detect_ext(filename: str) -> str:
    name = (filename or "").lower()
    if "." not in name:
        return ""
    return name[name.rfind(".") + 1:]


def read_text_from_bytes(data: bytes, filename: str) -> Optional[ExtractResult]:
    """
    Best-effort text reader for files that should be readable as text.

    Returns None for unsupported binary formats so callers can fall back to
    raw bytes/base64 behavior.
    """
    ext = _detect_ext(filename)
    if ext in _TEXT_EXTENSIONS:
        text, enc, warn = _decode_best_effort(data)
        return ExtractResult(text=text, kind=f"txt({enc})", meta={"encoding": enc}, warnings=warn)
    if ext == "docx":
        return DocxExtractor().extract(data, filename)
    if ext == "doc":
        return DocExtractor().extract(data, filename)
    return None
