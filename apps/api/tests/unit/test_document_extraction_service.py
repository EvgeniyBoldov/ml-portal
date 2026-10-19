from __future__ import annotations

import pytest

from app.services.document_extraction_service import (
    DocumentExtractionService,
    ExtractionRequest,
)
from app.services.extractors import ExtractResult


def test_detect_format_prefers_pdf_signature_over_filename() -> None:
    detected = DocumentExtractionService.detect_format(
        b"%PDF-1.7\n", filename="report.txt", content_type="text/plain"
    )
    assert detected.endswith(".pdf")


def test_detect_format_uses_declared_text_mime_for_unknown_extension() -> None:
    detected = DocumentExtractionService.detect_format(
        b"hello", filename="report.unknown", content_type="text/plain"
    )
    assert detected.endswith(".txt")


def test_detect_format_rejects_unknown_binary() -> None:
    detected = DocumentExtractionService.detect_format(
        b"\x00\x01\x02\xff", filename="payload.unknown", content_type="application/octet-stream"
    )
    assert detected is None


@pytest.mark.asyncio
async def test_chat_preview_is_bounded() -> None:
    result = await DocumentExtractionService().extract(
        ExtractionRequest(
            payload=b"abcdef",
            filename="sample.txt",
            profile="chat_preview",
            max_chars=3,
        )
    )
    assert result.text == "abc"
    assert result.truncated is True
    assert result.content_kind == "text"


@pytest.mark.asyncio
async def test_unknown_binary_returns_safe_metadata() -> None:
    result = await DocumentExtractionService().extract(
        ExtractionRequest(
            payload=b"\x00\x01\x02",
            filename="sample.bin",
            content_type="application/octet-stream",
        )
    )
    assert result.content_kind == "binary"
    assert result.text == ""
    assert result.parser == "unsupported"


@pytest.mark.asyncio
async def test_extraction_observer_gets_terminal_summary() -> None:
    events: list[tuple[str, dict]] = []

    async def observe(stage: str, payload: dict) -> None:
        events.append((stage, payload))

    await DocumentExtractionService().extract(
        ExtractionRequest(payload=b"hello", filename="sample.txt", observer=observe)
    )

    assert [stage for stage, _ in events] == ["started", "completed"]
    assert events[-1][1]["parser"] in {"docling", "txt(ascii)"}


@pytest.mark.asyncio
async def test_docling_is_primary_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    async def docling(_request: ExtractionRequest, _filename: str) -> ExtractResult:
        return ExtractResult(text="# Parsed by Docling", kind="docling")

    def fallback(_request: ExtractionRequest, _filename: str) -> ExtractResult:
        raise AssertionError("local extractor should not run after successful Docling conversion")

    monkeypatch.setattr(DocumentExtractionService, "_extract_docling", staticmethod(docling))
    monkeypatch.setattr(DocumentExtractionService, "_extract_fallback", staticmethod(fallback))
    result = await DocumentExtractionService().extract(
        ExtractionRequest(payload=b"file", filename="sample.pdf")
    )
    assert result.text == "# Parsed by Docling"
    assert result.parser == "docling"


@pytest.mark.asyncio
async def test_local_extractor_is_used_when_docling_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def docling(_request: ExtractionRequest, _filename: str) -> ExtractResult:
        raise TimeoutError("Docling did not respond")

    monkeypatch.setattr(DocumentExtractionService, "_extract_docling", staticmethod(docling))
    result = await DocumentExtractionService().extract(
        ExtractionRequest(payload=b"hello", filename="sample.txt")
    )
    assert result.text == "hello"
    assert result.parser == "txt(ascii)"
    assert any("Docling conversion failed" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_layout_extractor_is_preserved_as_pdf_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def docling(_request: ExtractionRequest, _filename: str) -> ExtractResult:
        raise ConnectionError("Docling unavailable")

    class LayoutFallback:
        kind = "pdf(layout-pdfminer)"

        def extract(self, payload: bytes, filename: str) -> ExtractResult:
            assert payload == b"%PDF-test"
            assert filename == "sample.pdf"
            return ExtractResult(text="layout fallback", kind=self.kind)

    monkeypatch.setattr(DocumentExtractionService, "_extract_docling", staticmethod(docling))
    result = await DocumentExtractionService().extract(
        ExtractionRequest(payload=b"%PDF-test", filename="sample.pdf", fallback_extractor=LayoutFallback())
    )
    assert result.text == "layout fallback"
    assert result.parser == "pdf(layout-pdfminer)"


@pytest.mark.asyncio
async def test_unsupported_format_does_not_decode_binary_as_text_after_docling_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def docling(_request: ExtractionRequest, _filename: str) -> ExtractResult:
        raise ConnectionError("Docling unavailable")

    monkeypatch.setattr(DocumentExtractionService, "_extract_docling", staticmethod(docling))
    result = await DocumentExtractionService().extract(
        ExtractionRequest(payload=b"\x00\x01", filename="slide.pptx")
    )
    assert result.text == ""
    assert result.parser == "unsupported"
