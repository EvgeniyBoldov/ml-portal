"""
Unit тесты для моделей анализа.
"""
import pytest
from datetime import datetime
import uuid
from app.models.analyze import AnalysisDocuments, AnalysisChunks


class TestAnalyzeModel:
    """Unit тесты для моделей анализа."""

    def test_analysis_documents_model_creation(self):
        """Тест создания модели AnalysisDocuments."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "status": "queued",
            "uploaded_by": uuid.uuid4(),
            "url_file": "https://example.com/document.pdf",
            "version": 1
        }

        # Act
        document = AnalysisDocuments(**document_data)

        # Assert
        assert document.id == document_data["id"]
        assert document.tenant_id == document_data["tenant_id"]
        assert document.status == "queued"
        assert document.uploaded_by == document_data["uploaded_by"]
        assert document.url_file == "https://example.com/document.pdf"
        assert document.version == 1

    def test_analysis_chunks_model_creation(self):
        """Тест создания модели AnalysisChunks."""
        # Arrange
        import uuid
        chunk_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "chunk_idx": 1,
            "text": "This is a test chunk of text.",
            "embedding_model": "text-embedding-ada-002",
            "version": 1
        }

        # Act
        chunk = AnalysisChunks(**chunk_data)

        # Assert
        assert chunk.id == chunk_data["id"]
        assert chunk.tenant_id == chunk_data["tenant_id"]
        assert chunk.document_id == chunk_data["document_id"]
        assert chunk.chunk_idx == 1
        assert chunk.text == "This is a test chunk of text."
        assert chunk.embedding_model == "text-embedding-ada-002"
        assert chunk.version == 1

    def test_analysis_documents_with_optional_fields(self):
        """Тест создания модели AnalysisDocuments с опциональными полями."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "status": "done",
            "url_file": "https://example.com/document.pdf",
            "url_canonical_file": "https://example.com/canonical.pdf",
            "result": {"summary": "Document processed successfully"},
            "version": 2
        }

        # Act
        document = AnalysisDocuments(**document_data)

        # Assert
        assert document.id == document_data["id"]
        assert document.status == "done"
        assert document.url_file == "https://example.com/document.pdf"
        assert document.url_canonical_file == "https://example.com/canonical.pdf"
        assert document.result == {"summary": "Document processed successfully"}
        assert document.version == 2

    def test_analysis_chunks_with_optional_fields(self):
        """Тест создания модели AnalysisChunks с опциональными полями."""
        # Arrange
        import uuid
        chunk_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "chunk_idx": 2,
            "text": "This is another test chunk.",
            "embedding_model": "text-embedding-ada-002",
            "embedding_version": "v1",
            "meta": {"confidence": 0.95}
        }

        # Act
        chunk = AnalysisChunks(**chunk_data)

        # Assert
        assert chunk.id == chunk_data["id"]
        assert chunk.chunk_idx == 2
        assert chunk.text == "This is another test chunk."
        assert chunk.embedding_model == "text-embedding-ada-002"
        assert chunk.embedding_version == "v1"
        assert chunk.meta == {"confidence": 0.95}
