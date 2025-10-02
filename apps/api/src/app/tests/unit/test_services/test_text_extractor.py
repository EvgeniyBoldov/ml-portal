"""
Unit тесты для TextExtractor.
"""
import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO
import json


class TestTextExtractor:
    """Unit тесты для TextExtractor."""

    def test_extract_result_dataclass(self):
        """Тест dataclass ExtractResult."""
        # Arrange
        from app.services.text_extractor import ExtractResult
        
        text = "Test text content"
        kind = "pdf"
        meta = {"pages": 1, "size": 1024}
        warnings = ["Warning 1", "Warning 2"]

        # Act
        result = ExtractResult(text=text, kind=kind, meta=meta, warnings=warnings)

        # Assert
        assert result.text == text
        assert result.kind == kind
        assert result.meta == meta
        assert result.warnings == warnings

    def test_extract_result_to_json(self):
        """Тест метода to_json ExtractResult."""
        # Arrange
        from app.services.text_extractor import ExtractResult
        
        text = "Test text content"
        kind = "pdf"
        meta = {"pages": 1, "size": 1024}
        warnings = ["Warning 1"]

        result = ExtractResult(text=text, kind=kind, meta=meta, warnings=warnings)

        # Act
        json_str = result.to_json()

        # Assert
        assert isinstance(json_str, str)
        json_data = json.loads(json_str)
        assert json_data["text"] == text
        assert json_data["type"] == "text"
        assert json_data["extractor"] == kind
        assert json_data["meta"] == meta
        assert json_data["warnings"] == warnings

    def test_detect_ext_with_extension(self):
        """Тест определения расширения файла."""
        # Arrange
        from app.services.text_extractor import _detect_ext

        # Act & Assert
        assert _detect_ext("document.pdf") == "pdf"
        assert _detect_ext("text.txt") == "txt"
        assert _detect_ext("data.docx") == "docx"
        assert _detect_ext("spreadsheet.xlsx") == "xlsx"
        assert _detect_ext("presentation.pptx") == "pptx"

    def test_detect_ext_without_extension(self):
        """Тест определения расширения файла без расширения."""
        # Arrange
        from app.services.text_extractor import _detect_ext

        # Act & Assert
        assert _detect_ext("document") == ""
        assert _detect_ext("") == ""
        assert _detect_ext(None) == ""

    def test_detect_ext_case_insensitive(self):
        """Тест определения расширения файла без учета регистра."""
        # Arrange
        from app.services.text_extractor import _detect_ext

        # Act & Assert
        assert _detect_ext("Document.PDF") == "pdf"
        assert _detect_ext("TEXT.TXT") == "txt"
        assert _detect_ext("Data.DOCX") == "docx"

    def test_decode_best_effort_utf8(self):
        """Тест декодирования UTF-8 текста."""
        # Arrange
        from app.services.text_extractor import _decode_best_effort
        
        test_text = "Привет, мир! Hello, world!"
        test_bytes = test_text.encode('utf-8')

        # Act
        decoded_text, encoding, warnings = _decode_best_effort(test_bytes)

        # Assert
        assert decoded_text == test_text
        assert encoding in ['utf-8', 'utf_8']
        assert isinstance(warnings, list)

    def test_decode_best_effort_with_charset_normalizer(self):
        """Тест декодирования с charset-normalizer."""
        # Arrange
        from app.services.text_extractor import _decode_best_effort
        
        test_text = "Test text with special chars: àáâãäå"
        test_bytes = test_text.encode('utf-8')

        # Act
        decoded_text, encoding, warnings = _decode_best_effort(test_bytes)

        # Assert
        assert isinstance(decoded_text, str)
        assert isinstance(encoding, str)
        assert isinstance(warnings, list)
        assert decoded_text == test_text or "Test text" in decoded_text

    def test_extract_text_unsupported_format(self):
        """Тест извлечения текста из неподдерживаемого формата."""
        # Arrange
        from app.services.text_extractor import extract_text
        
        test_data = b"Some binary data"
        filename = "file.xyz"

        # Act
        result = extract_text(test_data, filename)

        # Assert
        assert result.text == "Some binary data"  # Обрабатывается как текст
        assert len(result.warnings) > 0  # Должны быть предупреждения

    def test_extract_text_txt_format(self):
        """Тест извлечения текста из TXT файла."""
        # Arrange
        from app.services.text_extractor import extract_text
        
        test_text = "This is a test text file."
        test_data = test_text.encode('utf-8')
        filename = "test.txt"

        # Act
        result = extract_text(test_data, filename)

        # Assert
        assert result.text == test_text
        assert result.kind == "txt(utf-8)"  # Реальный формат
        assert isinstance(result.meta, dict)
        assert isinstance(result.warnings, list)

    def test_extract_text_csv_format(self):
        """Тест извлечения текста из CSV файла."""
        # Arrange
        from app.services.text_extractor import extract_text
        
        csv_data = "Name,Age,City\nJohn,25,New York\nJane,30,London"
        test_data = csv_data.encode('utf-8')
        filename = "data.csv"

        # Act
        result = extract_text(test_data, filename)

        # Assert
        assert "John" in result.text
        assert "Jane" in result.text
        assert result.kind == "csv(utf-8)"  # Реальный формат
        assert isinstance(result.meta, dict)
        assert isinstance(result.warnings, list)

    def test_extract_text_json_format(self):
        """Тест извлечения текста из JSON файла."""
        # Arrange
        from app.services.text_extractor import extract_text
        
        json_data = {"name": "John", "age": 25, "city": "New York"}
        test_data = json.dumps(json_data).encode('utf-8')
        filename = "data.json"

        # Act
        result = extract_text(test_data, filename)

        # Assert
        assert "John" in result.text
        assert result.kind == "txt(utf-8)"  # JSON обрабатывается как текст
        assert isinstance(result.meta, dict)
        assert isinstance(result.warnings, list)

    def test_extract_text_with_mock_pdf(self):
        """Тест извлечения текста из PDF с моком."""
        # Arrange
        from app.services.text_extractor import extract_text, ExtractResult
        
        test_data = b"PDF binary data"
        filename = "document.pdf"

        # Act
        with patch('app.services.text_extractor._extract_pdf') as mock_pdf:
            mock_result = ExtractResult("Extracted PDF text", "pdf", {"pages": 1}, [])
            mock_pdf.return_value = mock_result
            
            result = extract_text(test_data, filename)

        # Assert
        assert result.text == "Extracted PDF text"
        assert result.kind == "pdf"
        assert result.meta == {"pages": 1}
        assert result.warnings == []

    def test_extract_text_with_mock_docx(self):
        """Тест извлечения текста из DOCX с моком."""
        # Arrange
        from app.services.text_extractor import extract_text, ExtractResult
        
        test_data = b"DOCX binary data"
        filename = "document.docx"

        # Act
        with patch('app.services.text_extractor._extract_docx') as mock_docx:
            mock_result = ExtractResult("Extracted DOCX text", "docx", {"paragraphs": 5}, [])
            mock_docx.return_value = mock_result
            
            result = extract_text(test_data, filename)

        # Assert
        assert result.text == "Extracted DOCX text"
        assert result.kind == "docx"
        assert result.meta == {"paragraphs": 5}
        assert result.warnings == []

    def test_text_extractor_functions_exist(self):
        """Тест существования функций TextExtractor."""
        # Arrange
        from app.services.text_extractor import (
            extract_text, _detect_ext, _decode_best_effort,
            _extract_pdf, _extract_docx, _extract_xlsx
        )

        # Assert
        assert callable(extract_text)
        assert callable(_detect_ext)
        assert callable(_decode_best_effort)
        assert callable(_extract_pdf)
        assert callable(_extract_docx)
        assert callable(_extract_xlsx)
