"""Plain text extractor (txt, log, md, and fallback for unknown extensions)."""
from __future__ import annotations

from typing import List, Set, Tuple

from app.services.extractors.base import BaseExtractor, ExtractResult


def _decode_best_effort(data: bytes) -> Tuple[str, str, List[str]]:
    """Decode bytes to str using charset-normalizer (fallback to utf-8)."""
    warnings: List[str] = []
    try:
        from charset_normalizer import from_bytes as cn_from_bytes  # type: ignore

        res = cn_from_bytes(data).best()
        if res is not None:
            return str(res), (res.encoding or "utf-8"), warnings
        warnings.append("charset-normalizer: no best match, fallback to utf-8.")
        return data.decode("utf-8", errors="replace"), "utf-8", warnings
    except Exception as e:
        warnings.append(f"charset-normalizer unavailable ({e!r}); fallback to utf-8.")
        return data.decode("utf-8", errors="replace"), "utf-8", warnings


class TextExtractor(BaseExtractor):
    """Handles plain text files and acts as fallback for unknown extensions."""

    @property
    def extensions(self) -> Set[str]:
        return {"txt", "log", "md", ""}

    @property
    def kind(self) -> str:
        return "txt"

    def extract(self, data: bytes, filename: str) -> ExtractResult:
        text, enc, warn = _decode_best_effort(data)
        return ExtractResult(text=text, kind=f"txt({enc})", meta={"encoding": enc}, warnings=warn)
