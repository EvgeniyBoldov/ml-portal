"""
Layout-aware PDF extractor.

Uses DocTR (Document Text Recognition) for structure-preserving extraction:
- Detects text blocks, tables, headings via layout analysis
- Falls back to standard PdfExtractor if DocTR is unavailable

Activated when tenant.layout=True.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Set

from app.core.logging import get_logger
from app.services.extractors.base import BaseExtractor, ExtractResult

logger = get_logger(__name__)


def _doctr_available() -> bool:
    """Check if DocTR is installed and usable."""
    try:
        from doctr.io import DocumentFile  # type: ignore  # noqa: F401
        from doctr.models import ocr_predictor  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_with_doctr(data: bytes, engine_config: Dict[str, Any] | None = None) -> ExtractResult:
    """Run DocTR OCR pipeline on PDF bytes."""
    from doctr.io import DocumentFile  # type: ignore
    from doctr.models import ocr_predictor  # type: ignore

    warnings: List[str] = []
    doc = DocumentFile.from_pdf(data)

    engine_config = engine_config or {}
    det_arch = engine_config.get("det_arch", "db_resnet50")
    reco_arch = engine_config.get("reco_arch", "crnn_vgg16_bn")
    pretrained = engine_config.get("pretrained", True)

    predictor = ocr_predictor(
        det_arch=det_arch,
        reco_arch=reco_arch,
        pretrained=pretrained,
    )
    result = predictor(doc)

    pages_text: List[str] = []
    total_blocks = 0
    total_words = 0

    for page_idx, page in enumerate(result.pages):
        blocks: List[str] = []
        for block in page.blocks:
            block_lines: List[str] = []
            for line in block.lines:
                words = [w.value for w in line.words if w.value.strip()]
                total_words += len(words)
                if words:
                    block_lines.append(" ".join(words))
            if block_lines:
                blocks.append("\n".join(block_lines))
                total_blocks += 1
        pages_text.append("\n\n".join(blocks))

    text = "\n\n---\n\n".join(pages_text)  # page separator

    if not text.strip():
        warnings.append("DocTR produced no text. PDF may be image-only without recognizable text.")

    meta: Dict[str, Any] = {
        "pages": len(result.pages),
        "blocks": total_blocks,
        "words": total_words,
        "engine": "doctr",
    }

    return ExtractResult(text=text, kind="pdf(layout)", meta=meta, warnings=warnings)


def _extract_with_pdfminer_structured(data: bytes) -> ExtractResult:
    """
    Lightweight layout extraction using pdfminer's LAParams.
    Better than default pdfminer for preserving columns/structure
    but not as good as DocTR for scanned/complex PDFs.
    """
    warnings: List[str] = []
    text = ""
    pages = 0

    try:
        from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore
        from pdfminer.layout import LAParams  # type: ignore

        # Tuned LAParams for better structure preservation
        laparams = LAParams(
            line_margin=0.5,
            word_margin=0.1,
            char_margin=2.0,
            boxes_flow=0.5,  # Enable layout analysis
            detect_vertical=False,
        )

        text = pdf_extract_text(BytesIO(data), laparams=laparams) or ""

        try:
            import PyPDF2  # type: ignore
            r = PyPDF2.PdfReader(BytesIO(data))
            pages = len(r.pages)
        except Exception:
            pass

        if not text.strip():
            warnings.append("Layout extraction yielded no text. Consider enabling OCR.")

    except Exception as e:
        warnings.append(f"Layout extraction via pdfminer failed: {e!r}")

    return ExtractResult(
        text=text,
        kind="pdf(layout-pdfminer)",
        meta={"pages": pages, "engine": "pdfminer-layout"},
        warnings=warnings,
    )


class LayoutPdfExtractor(BaseExtractor):
    """
    Layout-aware PDF extractor.

    Strategy:
    1. If DocTR is available → use full OCR+layout pipeline
    2. Else → use pdfminer with tuned LAParams for structure preservation
    """

    def __init__(self, engine_config: Dict[str, Any] | None = None):
        self.engine_config = engine_config or {}

    @property
    def extensions(self) -> Set[str]:
        return {"pdf"}

    @property
    def kind(self) -> str:
        return "pdf(layout)"

    def extract(self, data: bytes, filename: str) -> ExtractResult:
        if _doctr_available():
            logger.info(f"Using DocTR layout extraction for {filename}")
            try:
                return _extract_with_doctr(data, self.engine_config)
            except Exception as e:
                logger.warning(f"DocTR failed for {filename}: {e!r}, falling back to pdfminer-layout")

        logger.info(f"Using pdfminer-layout extraction for {filename}")
        return _extract_with_pdfminer_structured(data)
