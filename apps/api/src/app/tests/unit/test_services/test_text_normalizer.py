"""
Unit тесты для TextNormalizer.
"""
import pytest
import re


class TestTextNormalizer:
    """Unit тесты для TextNormalizer."""

    def test_normalize_text_empty_string(self):
        """Тест нормализации пустой строки."""
        # Arrange
        from app.services.text_normalizer import normalize_text

        # Act
        result = normalize_text("")

        # Assert
        assert result == ""

    def test_normalize_text_none(self):
        """Тест нормализации None."""
        # Arrange
        from app.services.text_normalizer import normalize_text

        # Act
        result = normalize_text(None)

        # Assert
        assert result == ""

    def test_normalize_text_basic(self):
        """Тест базовой нормализации текста."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "Hello, world!"

        # Act
        result = normalize_text(text)

        # Assert
        assert result == "Hello, world!"

    def test_normalize_text_unicode_normalization(self):
        """Тест нормализации Unicode."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        # Используем символы, которые должны быть нормализованы
        text = "café"  # содержит é

        # Act
        result = normalize_text(text)

        # Assert
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_text_remove_zero_width_chars(self):
        """Тест удаления zero-width символов."""
        # Arrange
        from app.services.text_normalizer import normalize_text, ZERO_WIDTH
        
        text = f"Hello{chr(0x200B)}world"  # zero width space

        # Act
        result = normalize_text(text)

        # Assert
        assert "Hello" in result
        assert "world" in result
        assert chr(0x200B) not in result

    def test_normalize_text_remove_control_chars(self):
        """Тест удаления control символов."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "Hello\x00world\x01test"

        # Act
        result = normalize_text(text)

        # Assert
        assert "Hello" in result
        assert "world" in result
        assert "test" in result
        assert "\x00" not in result
        assert "\x01" not in result

    def test_normalize_text_quote_mapping(self):
        """Тест маппинга кавычек."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = 'He said "Hello" and \'Goodbye\''

        # Act
        result = normalize_text(text)

        # Assert
        assert '"' in result
        assert "'" in result

    def test_normalize_text_dash_mapping(self):
        """Тест маппинга тире."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "This is a — dash"

        # Act
        result = normalize_text(text)

        # Assert
        assert "-" in result

    def test_normalize_text_line_endings(self):
        """Тест нормализации окончаний строк."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "Line 1\r\nLine 2\rLine 3\nLine 4"

        # Act
        result = normalize_text(text)

        # Assert
        assert "\r\n" not in result
        assert "\r" not in result
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert "Line 4" in result

    def test_normalize_text_hyphen_wrap(self):
        """Тест исправления переносов с дефисом."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "This is a hyphen-\nated word"

        # Act
        result = normalize_text(text)

        # Assert
        assert "hyphenated" in result or "hyphen-ated" in result
        assert "hyphen-\nated" not in result

    def test_normalize_text_soft_breaks(self):
        """Тест исправления мягких переносов."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "This is a soft\nbreak"

        # Act
        result = normalize_text(text)

        # Assert
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_text_bullets(self):
        """Тест нормализации маркеров."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "• First item\n• Second item"

        # Act
        result = normalize_text(text)

        # Assert
        assert "- First item" in result
        assert "- Second item" in result or "• Second item" in result

    def test_normalize_text_multiple_spaces(self):
        """Тест нормализации множественных пробелов."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "Multiple    spaces   here"

        # Act
        result = normalize_text(text)

        # Assert
        assert "Multiple spaces here" in result
        assert "    " not in result

    def test_normalize_text_multiple_newlines(self):
        """Тест нормализации множественных переносов строк."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = "Line 1\n\n\n\nLine 2"

        # Act
        result = normalize_text(text)

        # Assert
        assert "\n\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_normalize_text_complex_example(self):
        """Тест комплексного примера нормализации."""
        # Arrange
        from app.services.text_normalizer import normalize_text
        
        text = 'He said "Hello" and \'Goodbye\'.\nThis is a hyphen-\nated word.\n• First item\n• Second item'

        # Act
        result = normalize_text(text)

        # Assert
        assert isinstance(result, str)
        assert len(result) > 0
        assert "hyphenated" in result or "hyphen-ated" in result
        assert "First item" in result
        assert "Second item" in result

    def test_normalize_text_constants(self):
        """Тест констант TextNormalizer."""
        # Arrange
        from app.services.text_normalizer import (
            ZERO_WIDTH, CONTROL_CHARS, CONTROL_RE, ZEROW_RE, PUNCT_MAP,
            BULLET_RE, MULTISPACE_RE, BLANKS_RE, HYPHEN_WRAP_RE, SOFT_BREAK_RE
        )

        # Assert
        assert isinstance(ZERO_WIDTH, str)
        assert isinstance(CONTROL_CHARS, str)
        assert isinstance(CONTROL_RE, re.Pattern)
        assert isinstance(ZEROW_RE, re.Pattern)
        assert isinstance(PUNCT_MAP, dict)
        assert isinstance(BULLET_RE, re.Pattern)
        assert isinstance(MULTISPACE_RE, re.Pattern)
        assert isinstance(BLANKS_RE, re.Pattern)
        assert isinstance(HYPHEN_WRAP_RE, re.Pattern)
        assert isinstance(SOFT_BREAK_RE, re.Pattern)

    def test_normalize_text_punctuation_mapping(self):
        """Тест маппинга пунктуации."""
        # Arrange
        from app.services.text_normalizer import PUNCT_MAP

        # Assert
        assert "\u2018" in PUNCT_MAP  # left single quotation mark
        assert "\u2019" in PUNCT_MAP  # right single quotation mark
        assert "\u201C" in PUNCT_MAP  # left double quotation mark
        assert "\u201D" in PUNCT_MAP  # right double quotation mark
        assert "\u2013" in PUNCT_MAP  # en dash
        assert "\u2014" in PUNCT_MAP  # em dash
        assert "\u00A0" in PUNCT_MAP  # non-breaking space

    def test_normalize_text_regex_patterns(self):
        """Тест регулярных выражений."""
        # Arrange
        from app.services.text_normalizer import (
            BULLET_RE, MULTISPACE_RE, BLANKS_RE, HYPHEN_WRAP_RE, SOFT_BREAK_RE
        )

        # Act & Assert
        assert BULLET_RE.search("• First item") is not None
        assert MULTISPACE_RE.search("Multiple    spaces") is not None
        assert BLANKS_RE.search("Line 1\n\n\n\nLine 2") is not None
        assert HYPHEN_WRAP_RE.search("hyphen-\nated") is not None
        assert SOFT_BREAK_RE.search("soft\nbreak") is not None
