"""
Base extractor interface and ExtractResult dataclass.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class ExtractResult:
    """Result of text extraction from a document."""
    text: str
    kind: str
    meta: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "text": self.text,
                "type": "text",
                "extractor": self.kind,
                "meta": self.meta,
                "warnings": self.warnings,
            },
            ensure_ascii=False,
        )


class BaseExtractor(ABC):
    """
    Abstract base class for document extractors.

    Each extractor declares which file extensions it supports
    and implements the extract() method.
    """

    @property
    @abstractmethod
    def extensions(self) -> Set[str]:
        """Set of file extensions this extractor handles (without dot, lowercase)."""
        ...

    @property
    @abstractmethod
    def kind(self) -> str:
        """Short identifier for this extractor (e.g. 'pdf', 'docx', 'txt')."""
        ...

    @abstractmethod
    def extract(self, data: bytes, filename: str) -> ExtractResult:
        """
        Extract text from raw file bytes.

        Args:
            data: Raw file content.
            filename: Original filename (used for extension detection, metadata).

        Returns:
            ExtractResult with extracted text, kind, meta, and warnings.
        """
        ...
