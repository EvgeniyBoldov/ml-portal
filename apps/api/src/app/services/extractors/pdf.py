"""PDF text extractor using pdfminer.six with PyPDF2 fallback."""
from __future__ import annotations

from io import BytesIO
from typing import List, Set

from app.services.extractors.base import BaseExtractor, ExtractResult


class PdfExtractor(BaseExtractor):
    """Extracts text from PDF files via pdfminer.six (with PyPDF2 fallback)."""

    @property
    def extensions(self) -> Set[str]:
        return {"pdf"}

    @property
    def kind(self) -> str:
        return "pdf"

    def extract(self, data: bytes, filename: str) -> ExtractResult:
        warnings: List[str] = []
        text = ""
        pages = 0

        try:
            from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore

            text = pdf_extract_text(BytesIO(data)) or ""
            try:
                import PyPDF2  # type: ignore

                r = PyPDF2.PdfReader(BytesIO(data))
                pages = len(r.pages)
            except Exception:
                pages = 0
            if not text.strip():
                warnings.append(
                    "PDF appears to have no extractable text (maybe scanned). Consider OCR later."
                )
        except Exception as e:
            warnings.append(f"PDF extraction failed via pdfminer: {e!r}")
            try:
                import PyPDF2  # type: ignore

                r = PyPDF2.PdfReader(BytesIO(data))
                pages = len(r.pages)
                text = ""
                for p in r.pages:
                    try:
                        text += (p.extract_text() or "") + "\n"
                    except Exception:
                        continue
                if not text.strip():
                    warnings.append("PyPDF2 yielded empty text. Consider OCR.")
            except Exception as e2:
                warnings.append(f"PyPDF2 fallback failed: {e2!r}")
                text = ""

        return ExtractResult(
            text=text, kind="pdf", meta={"pages": pages}, warnings=warnings
        )
