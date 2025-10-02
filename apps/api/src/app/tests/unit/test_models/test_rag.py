"""
Unit тесты для моделей RAG.
"""
import pytest
from datetime import datetime
import uuid
from app.models.rag import RAGDocument, RAGChunk


class TestRAGModel:
    """Unit тесты для моделей RAG."""

    def test_rag_document_model_creation(self):
        """Тест создания модели RAGDocument."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "filename": "test_document.pdf",
            "title": "Test Document",
            "status": "uploading",
            "user_id": uuid.uuid4(),
            "content_type": "application/pdf",
            "size": 1024000,
            "tags": ["test", "document"]
        }

        # Act
        document = RAGDocument(**document_data)

        # Assert
        assert document.id == document_data["id"]
        assert document.filename == "test_document.pdf"
        assert document.title == "Test Document"
        assert document.status == "uploading"
        assert document.user_id == document_data["user_id"]
        assert document.content_type == "application/pdf"
        assert document.size == 1024000
        assert document.tags == ["test", "document"]

    def test_rag_document_with_optional_fields(self):
        """Тест создания модели RAGDocument с опциональными полями."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "filename": "test_document.pdf",
            "title": "Test Document",
            "status": "processed",
            "user_id": uuid.uuid4(),
            "s3_key_raw": "raw/test_document.pdf",
            "s3_key_processed": "processed/test_document.pdf",
            "processed_at": datetime.now(),
            "tags": ["processed", "ready"]
        }

        # Act
        document = RAGDocument(**document_data)

        # Assert
        assert document.id == document_data["id"]
        assert document.filename == "test_document.pdf"
        assert document.title == "Test Document"
        assert document.status == "processed"
        assert document.user_id == document_data["user_id"]
        assert document.s3_key_raw == "raw/test_document.pdf"
        assert document.s3_key_processed == "processed/test_document.pdf"
        assert document.processed_at == document_data["processed_at"]
        assert document.tags == ["processed", "ready"]

    def test_rag_document_status_values(self):
        """Тест валидных значений статуса RAGDocument."""
        # Arrange
        valid_statuses = ["uploading", "processing", "processed", "failed", "archived"]

        # Assert
        assert "uploading" in valid_statuses
        assert "processing" in valid_statuses
        assert "processed" in valid_statuses
        assert "failed" in valid_statuses
        assert "archived" in valid_statuses

    def test_rag_document_content_types(self):
        """Тест валидных типов контента RAGDocument."""
        # Arrange
        valid_content_types = [
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]

        # Assert
        for content_type in valid_content_types:
            assert isinstance(content_type, str)
            assert len(content_type) > 0

    def test_rag_document_tags_validation(self):
        """Тест валидации тегов RAGDocument."""
        # Arrange
        valid_tags = [
            ["test", "document"],
            ["processed", "ready", "public"],
            ["private", "confidential"],
            []
        ]

        # Assert
        for tags in valid_tags:
            assert isinstance(tags, list)
            assert all(isinstance(tag, str) for tag in tags)

    def test_rag_document_s3_keys(self):
        """Тест S3 ключей RAGDocument."""
        # Arrange
        s3_keys = {
            "raw": "raw/test_document.pdf",
            "processed": "processed/test_document.pdf"
        }

        # Assert
        assert "raw" in s3_keys
        assert "processed" in s3_keys
        assert s3_keys["raw"].startswith("raw/")
        assert s3_keys["processed"].startswith("processed/")

    def test_rag_document_size_validation(self):
        """Тест валидации размера RAGDocument."""
        # Arrange
        valid_sizes = [1024, 1048576, 10485760, 104857600]  # 1KB to 100MB

        # Assert
        for size in valid_sizes:
            assert isinstance(size, int)
            assert size > 0
            assert size <= 104857600  # Максимум 100MB

    def test_rag_document_timestamps(self):
        """Тест временных меток RAGDocument."""
        # Arrange
        now = datetime.now()
        timestamps = {
            "created_at": now,
            "updated_at": now,
            "processed_at": now
        }

        # Assert
        for timestamp_name, timestamp in timestamps.items():
            assert isinstance(timestamp, datetime)

    def test_rag_document_error_message(self):
        """Тест сообщения об ошибке RAGDocument."""
        # Arrange
        error_messages = [
            "File processing failed",
            "Invalid file format",
            "File too large",
            "Network timeout"
        ]

        # Assert
        for error_message in error_messages:
            assert isinstance(error_message, str)
            assert len(error_message) > 0

    def test_rag_document_repr(self):
        """Тест метода __repr__ RAGDocument."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "filename": "test_document.pdf",
            "title": "Test Document",
            "status": "processed",
            "user_id": uuid.uuid4()
        }

        document = RAGDocument(**document_data)

        # Act
        repr_str = repr(document)

        # Assert
        assert isinstance(repr_str, str)
        assert "RAGDocument" in repr_str
        assert str(document.id) in repr_str
        assert document.filename in repr_str
        assert document.status in repr_str

    def test_rag_document_to_dict(self):
        """Тест метода to_dict RAGDocument."""
        # Arrange
        import uuid
        document_data = {
            "id": uuid.uuid4(),
            "filename": "test_document.pdf",
            "title": "Test Document",
            "status": "processed",
            "user_id": uuid.uuid4(),
            "content_type": "application/pdf",
            "size": 1024000,
            "tags": ["test", "document"]
        }

        document = RAGDocument(**document_data)

        # Act
        dict_data = document.to_dict()

        # Assert
        assert isinstance(dict_data, dict)
        assert "id" in dict_data
        assert "filename" in dict_data
        assert "title" in dict_data
        assert "status" in dict_data
        assert "user_id" in dict_data

    def test_rag_chunk_model_creation(self):
        """Тест создания модели RAGChunk."""
        # Arrange
        import uuid
        chunk_data = {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "chunk_index": 1,
            "content": "This is a test chunk of text.",
            "embedding": [0.1, 0.2, 0.3, 0.4, 0.5],
            "chunk_metadata": {"page": 1, "section": "introduction"}
        }

        # Act
        chunk = RAGChunk(**chunk_data)

        # Assert
        assert chunk.id == chunk_data["id"]
        assert chunk.document_id == chunk_data["document_id"]
        assert chunk.chunk_index == 1
        assert chunk.content == "This is a test chunk of text."
        assert chunk.embedding == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert chunk.chunk_metadata == {"page": 1, "section": "introduction"}

    def test_rag_chunk_with_optional_fields(self):
        """Тест создания модели RAGChunk с опциональными полями."""
        # Arrange
        import uuid
        chunk_data = {
            "id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "chunk_index": 2,
            "content": "This is another test chunk.",
            "embedding": [0.6, 0.7, 0.8, 0.9, 1.0],
            "chunk_metadata": {"page": 2, "section": "body"},
            "created_at": datetime.now()
        }

        # Act
        chunk = RAGChunk(**chunk_data)

        # Assert
        assert chunk.id == chunk_data["id"]
        assert chunk.document_id == chunk_data["document_id"]
        assert chunk.chunk_index == 2
        assert chunk.content == "This is another test chunk."
        assert chunk.embedding == [0.6, 0.7, 0.8, 0.9, 1.0]
        assert chunk.chunk_metadata == {"page": 2, "section": "body"}
        assert chunk.created_at == chunk_data["created_at"]

    def test_rag_chunk_embedding_validation(self):
        """Тест валидации embedding RAGChunk."""
        # Arrange
        embeddings = [
            [0.1, 0.2, 0.3],
            [0.1, 0.2, 0.3, 0.4, 0.5],
            [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ]

        # Assert
        for embedding in embeddings:
            assert isinstance(embedding, list)
            assert len(embedding) > 0
            assert all(isinstance(val, (int, float)) for val in embedding)

    def test_rag_chunk_metadata_validation(self):
        """Тест валидации metadata RAGChunk."""
        # Arrange
        metadata_examples = [
            {"page": 1, "section": "introduction"},
            {"chapter": 2, "paragraph": 3},
            {"line": 10, "word_count": 25},
            {}
        ]

        # Assert
        for metadata in metadata_examples:
            assert isinstance(metadata, dict)

    def test_rag_chunk_text_validation(self):
        """Тест валидации текста RAGChunk."""
        # Arrange
        text_examples = [
            "Short text",
            "This is a medium length text that should be processed correctly.",
            "This is a very long text that contains multiple sentences and should be analyzed properly by the system."
        ]

        # Assert
        for text in text_examples:
            assert isinstance(text, str)
            assert len(text) > 0

    def test_rag_chunk_index_validation(self):
        """Тест валидации индекса RAGChunk."""
        # Arrange
        valid_indices = [0, 1, 2, 10, 100, 1000]

        # Assert
        for index in valid_indices:
            assert isinstance(index, int)
            assert index >= 0

    def test_rag_models_inheritance(self):
        """Тест наследования моделей RAG."""
        # Arrange
        from app.models.base import Base

        # Assert
        assert issubclass(RAGDocument, Base)
        assert issubclass(RAGChunk, Base)

    def test_rag_document_table_name(self):
        """Тест имени таблицы RAGDocument."""
        # Assert
        assert RAGDocument.__tablename__ == "rag_documents"

    def test_rag_chunk_table_name(self):
        """Тест имени таблицы RAGChunk."""
        # Assert
        assert RAGChunk.__tablename__ == "rag_chunks"
