from __future__ import annotations

import pytest

from app.services.document_extraction_service import (
    DocumentExtractionService,
    ExtractionRequest,
)


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
    assert events[-1][1]["parser"] == "txt(ascii)"
