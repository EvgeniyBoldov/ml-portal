"""
ExtractorRegistry — singleton registry for document extractors.

Auto-registers built-in extractors on first use.
New extractors can be registered at runtime via register().
"""
from __future__ import annotations

from typing import Dict, List, Optional, Type

from app.core.logging import get_logger
from app.services.extractors.base import BaseExtractor, ExtractResult

logger = get_logger(__name__)


class ExtractorRegistry:
    """Registry mapping file extensions to extractors."""

    _extractors: Dict[str, BaseExtractor] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, extractor: BaseExtractor) -> None:
        """Register an extractor for its declared extensions."""
        for ext in extractor.extensions:
            existing = cls._extractors.get(ext)
            if existing:
                logger.info(
                    f"Overriding extractor for .{ext}: "
                    f"{existing.kind} -> {extractor.kind}"
                )
            cls._extractors[ext] = extractor
            logger.debug(f"Registered extractor '{extractor.kind}' for .{ext}")

    @classmethod
    def register_class(cls, extractor_cls: Type[BaseExtractor]) -> None:
        """Instantiate and register an extractor class."""
        cls.register(extractor_cls())

    @classmethod
    def get_extractor(cls, ext: str) -> Optional[BaseExtractor]:
        """Get extractor for a file extension (without dot, lowercase)."""
        cls._ensure_initialized()
        return cls._extractors.get(ext.lower())

    @classmethod
    def supported_extensions(cls) -> List[str]:
        """List all supported file extensions."""
        cls._ensure_initialized()
        return sorted(cls._extractors.keys())

    @classmethod
    def extract(cls, data: bytes, filename: str) -> ExtractResult:
        """
        Extract text from file data using the appropriate extractor.

        Falls back to text extractor for unknown extensions.
        This is the main entry point — drop-in replacement for
        the old text_extractor.extract_text() function.
        """
        cls._ensure_initialized()

        ext = _detect_ext(filename)
        extractor = cls._extractors.get(ext)

        if extractor:
            return extractor.extract(data, filename)

        # Fallback: try text extractor for unknown extensions
        txt_extractor = cls._extractors.get("")
        if txt_extractor:
            result = txt_extractor.extract(data, filename)
            result.warnings.append(f"Unknown extension '.{ext}', treated as text.")
            return result

        return ExtractResult(
            text="",
            kind="unknown",
            meta={},
            warnings=[f"No extractor found for extension '.{ext}'"],
        )

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Lazy-init: register built-in extractors on first access."""
        if cls._initialized:
            return
        cls._initialized = True
        _register_builtins(cls)


def _detect_ext(filename: str) -> str:
    """Extract file extension from filename (without dot, lowercase)."""
    name = (filename or "").lower()
    if "." not in name:
        return ""
    return name[name.rfind(".") + 1:]


def _register_builtins(registry: type) -> None:
    """Register all built-in extractors."""
    from app.services.extractors.text import TextExtractor
    from app.services.extractors.pdf import PdfExtractor
    from app.services.extractors.docx import DocxExtractor
    from app.services.extractors.csv_ext import CsvExtractor
    from app.services.extractors.xlsx import XlsxExtractor

    for cls in [TextExtractor, PdfExtractor, DocxExtractor, CsvExtractor, XlsxExtractor]:
        registry.register(cls())
