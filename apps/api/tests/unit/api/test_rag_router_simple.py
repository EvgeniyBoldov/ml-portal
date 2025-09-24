"""
Simple unit tests for RAG router
"""
import pytest
from unittest.mock import Mock

from app.api.routers.rag import _safe_ext
from app.models.rag import RAGDocument


class TestRagRouterSimple:
    """Test RAG router functions - simple version"""
    
    def setup_method(self):
        """Setup test method"""
        # Mock RAG document
        self.mock_document = Mock(spec=RAGDocument)
        self.mock_document.id = "doc123"
        self.mock_document.name = "test.pdf"
        self.mock_document.status = "processed"
        self.mock_document.tags = ["tag1", "tag2"]
        self.mock_document.url_file = "doc123/origin.pdf"
        self.mock_document.url_canonical_file = "doc123/canonical.txt"
        self.mock_document.created_at = "2023-01-01T00:00:00"
        self.mock_document.updated_at = "2023-01-01T00:00:00"
    
    def test_safe_ext_valid(self):
        """Test _safe_ext with valid filename"""
        result = _safe_ext("test.pdf")
        assert result == ".pdf"
    
    def test_safe_ext_no_extension(self):
        """Test _safe_ext with no extension"""
        result = _safe_ext("test")
        assert result == ""
    
    def test_safe_ext_none(self):
        """Test _safe_ext with None filename"""
        result = _safe_ext(None)
        assert result == ""
    
    def test_safe_ext_empty(self):
        """Test _safe_ext with empty filename"""
        result = _safe_ext("")
        assert result == ""
    
    def test_safe_ext_multiple_dots(self):
        """Test _safe_ext with multiple dots"""
        result = _safe_ext("test.backup.pdf")
        assert result == ".pdf"
