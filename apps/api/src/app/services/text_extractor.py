"""
Backward-compatible wrapper around ExtractorRegistry.

All extraction logic now lives in app.services.extractors.*.
This module re-exports ExtractResult and extract_text() so existing
imports continue to work without changes.
"""
from __future__ import annotations

from app.services.extractors.base import ExtractResult
from app.services.extractors.registry import ExtractorRegistry


def extract_text(data: bytes, filename: str) -> ExtractResult:
    """
    Universal text extractor for: PDF, DOCX, TXT, CSV, XLSX.
    Returns ExtractResult(text, kind, meta, warnings).

    Delegates to ExtractorRegistry — see app.services.extractors for details.
    """
    return ExtractorRegistry.extract(data, filename)


__all__ = ["ExtractResult", "extract_text"]
