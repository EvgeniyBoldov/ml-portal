from __future__ import annotations

import pytest

from app.services.file_formats import FileCodecRegistry


def test_supported_generation_formats_are_stable() -> None:
    assert FileCodecRegistry.supported_formats() == ("csv", "docx", "json", "md", "txt")


def test_json_codec_rejects_invalid_content() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        FileCodecRegistry.get("json").encode("{broken", "report")


def test_text_codec_normalizes_filename_and_metadata() -> None:
    encoded = FileCodecRegistry.get("txt").encode("hello", "report.csv")
    assert encoded.filename == "report.txt"
    assert encoded.content == b"hello"
    assert encoded.content_type == "text/plain"


def test_docx_codec_produces_office_bytes() -> None:
    pytest.importorskip("docx")
    encoded = FileCodecRegistry.get("docx").encode("First\n\nSecond", "report")
    assert encoded.filename == "report.docx"
    assert encoded.content[:2] == b"PK"
