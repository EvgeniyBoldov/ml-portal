"""Legacy DOC extractor with best-effort recovery paths.

This runtime does not ship a native DOC converter, so we try the safest
recoverable routes first:
- mislabeled ZIP-based files are treated as DOCX
- text-like payloads are decoded with charset-normalizer

If neither path works, the extractor returns an empty body with warnings so
callers can fail loudly or fall back to raw bytes, depending on context.
"""
from __future__ import annotations

import zipfile
from io import BytesIO
from typing import List, Set

from app.core.logging import get_logger
from app.services.extractors.base import BaseExtractor, ExtractResult
from app.services.extractors.text import _decode_best_effort

logger = get_logger(__name__)


def _looks_like_text(text: str) -> bool:
    if not text:
        return False
    sample = text[:4096]
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\r\t")
    return printable / max(len(sample), 1) >= 0.85


class DocExtractor(BaseExtractor):
    """Best-effort extractor for legacy DOC files."""

    @property
    def extensions(self) -> Set[str]:
        return {"doc"}

    @property
    def kind(self) -> str:
        return "doc"

    def extract(self, data: bytes, filename: str) -> ExtractResult:
        warnings: List[str] = []

        if zipfile.is_zipfile(BytesIO(data)):
            warnings.append("DOC payload looks like ZIP/docx content; using DOCX parser.")
            try:
                from app.services.extractors.docx import DocxExtractor

                result = DocxExtractor().extract(data, filename)
                result.warnings = warnings + result.warnings
                return result
            except Exception as exc:
                logger.error("DOCX fallback failed for %s: %s", filename, exc, exc_info=True)
                warnings.append(f"DOCX fallback failed: {exc!r}")

        try:
            text, enc, decode_warnings = _decode_best_effort(data)
            warnings.extend(decode_warnings)
            if _looks_like_text(text):
                return ExtractResult(text=text, kind=f"doc(text/{enc})", meta={"encoding": enc}, warnings=warnings)
            warnings.append("Decoded payload does not look like readable text.")
        except Exception as exc:
            logger.error("DOC text recovery failed for %s: %s", filename, exc, exc_info=True)
            warnings.append(f"DOC text recovery failed: {exc!r}")

        warnings.append(
            "Legacy binary DOC format is not natively supported in this runtime. "
            "Convert the file to DOCX for reliable extraction."
        )
        return ExtractResult(text="", kind="doc", meta={}, warnings=warnings)
