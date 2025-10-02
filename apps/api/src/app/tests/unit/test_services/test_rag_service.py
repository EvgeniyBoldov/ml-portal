"""
Unit тесты для RAGService.
"""
import pytest
from unittest.mock import MagicMock, patch
import uuid
from datetime import datetime


class TestRAGService:
    """Unit тесты для RAGService."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        return MagicMock()

    @pytest.fixture
    def rag_documents_service(self, mock_session):
        """Создает экземпляр RAGDocumentsService с моками."""
        with patch('app.services.rag_service.create_rag_documents_repository') as mock_docs_repo, \
             patch('app.services.rag_service.create_rag_chunks_repository') as mock_chunks_repo:
            
            mock_docs_repo_instance = MagicMock()
            mock_chunks_repo_instance = MagicMock()
            mock_docs_repo.return_value = mock_docs_repo_instance
            mock_chunks_repo.return_value = mock_chunks_repo_instance
            
            from app.services.rag_service import RAGDocumentsService
            return RAGDocumentsService(mock_session)

    def test_rag_documents_service_initialization(self, rag_documents_service, mock_session):
        """Тест инициализации RAGDocumentsService."""
        # Assert
        assert rag_documents_service.session == mock_session
        assert hasattr(rag_documents_service, 'documents_repo')
        assert hasattr(rag_documents_service, 'chunks_repo')

    def test_get_required_fields(self, rag_documents_service):
        """Тест получения обязательных полей."""
        # Act
        required_fields = rag_documents_service._get_required_fields()

        # Assert
        assert isinstance(required_fields, list)
        assert "filename" in required_fields
        assert "title" in required_fields
        assert "user_id" in required_fields

    def test_process_create_data(self, rag_documents_service):
        """Тест обработки данных для создания документа."""
        # Arrange
        data = {
            "filename": "  test_document.pdf  ",
            "title": "Test Document",
            "user_id": str(uuid.uuid4()),
            "description": "Test description"
        }

        # Act
        processed = rag_documents_service._process_create_data(data)

        # Assert
        assert processed["filename"] == "test_document.pdf"  # Должно быть обрезано
        assert processed["title"] == "Test Document"
        assert processed["user_id"] == data["user_id"]
        assert processed["description"] == "Test description"

    def test_sanitize_string(self, rag_documents_service):
        """Тест санитизации строки."""
        # Arrange
        test_string = "  Test String  "
        max_length = 10

        # Act
        result = rag_documents_service._sanitize_string(test_string, max_length)

        # Assert
        assert result == "Test Strin"  # Обрезано до max_length
        assert len(result) <= max_length

    def test_allowed_extensions(self):
        """Тест разрешенных расширений файлов."""
        # Arrange
        from app.services.rag_service import ALLOWED_EXTENSIONS

        # Assert
        assert '.txt' in ALLOWED_EXTENSIONS
        assert '.pdf' in ALLOWED_EXTENSIONS
        assert '.doc' in ALLOWED_EXTENSIONS
        assert '.docx' in ALLOWED_EXTENSIONS
        assert '.md' in ALLOWED_EXTENSIONS
        assert '.rtf' in ALLOWED_EXTENSIONS
        assert '.odt' in ALLOWED_EXTENSIONS
        assert '.html' in ALLOWED_EXTENSIONS
        assert '.htm' in ALLOWED_EXTENSIONS

    def test_max_file_size(self):
        """Тест максимального размера файла."""
        # Arrange
        from app.services.rag_service import MAX_FILE_SIZE

        # Assert
        assert MAX_FILE_SIZE == 100 * 1024 * 1024  # 100MB

    def test_rag_service_attributes(self, rag_documents_service):
        """Тест атрибутов RAGDocumentsService."""
        # Assert
        assert hasattr(rag_documents_service, 'session')
        assert hasattr(rag_documents_service, 'documents_repo')
        assert hasattr(rag_documents_service, 'chunks_repo')

    def test_rag_service_methods(self, rag_documents_service):
        """Тест методов RAGDocumentsService."""
        # Assert
        assert hasattr(rag_documents_service, '_get_required_fields')
        assert hasattr(rag_documents_service, '_process_create_data')
        assert hasattr(rag_documents_service, '_sanitize_string')
        assert callable(getattr(rag_documents_service, '_get_required_fields'))
        assert callable(getattr(rag_documents_service, '_process_create_data'))
        assert callable(getattr(rag_documents_service, '_sanitize_string'))

    def test_file_extension_validation(self):
        """Тест валидации расширения файла."""
        # Arrange
        from app.services.rag_service import ALLOWED_EXTENSIONS
        
        # Act & Assert
        valid_files = ["document.pdf", "text.txt", "data.docx", "readme.md"]
        for filename in valid_files:
            extension = '.' + filename.split('.')[-1]
            assert extension in ALLOWED_EXTENSIONS

    def test_file_size_validation(self):
        """Тест валидации размера файла."""
        # Arrange
        from app.services.rag_service import MAX_FILE_SIZE
        
        # Act & Assert
        small_file_size = 1024  # 1KB
        large_file_size = 200 * 1024 * 1024  # 200MB
        
        assert small_file_size < MAX_FILE_SIZE
        assert large_file_size > MAX_FILE_SIZE

    def test_rag_documents_service_inheritance(self, rag_documents_service):
        """Тест наследования RAGDocumentsService."""
        # Assert
        from app.services._base import RepositoryService
        assert isinstance(rag_documents_service, RepositoryService)
