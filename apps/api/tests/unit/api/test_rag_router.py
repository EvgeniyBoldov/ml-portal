"""
Unit tests for RAG router
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from app.api.routers.rag import (
    upload_rag_file, list_rag_documents, get_rag_document,
    update_rag_document_tags, search_rag, download_rag_file,
    get_rag_progress, archive_rag_document, delete_rag_document
)
from app.models.rag import RAGDocument


class TestRagRouter:
    """Test RAG router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock(spec=Session)
        self.mock_user = Mock()
        self.mock_user.id = "user123"
        self.mock_user.role = "editor"
        
        # Mock RAG document
        self.mock_document = Mock(spec=RAGDocument)
        self.mock_document.id = "doc123"
        self.mock_document.name = "test.pdf"
        self.mock_document.status = "processed"
        self.mock_document.tags = ["tag1", "tag2"]
        self.mock_document.url_file = "doc123/origin.pdf"
        self.mock_document.url_canonical_file = "doc123/canonical.txt"
        self.mock_document.date_upload = "2023-01-01T00:00:00"
        self.mock_document.created_at = "2023-01-01T00:00:00"
        self.mock_document.updated_at = "2023-01-01T00:00:00"
        
        # Mock upload file
        self.mock_file = Mock(spec=UploadFile)
        self.mock_file.filename = "test.pdf"
        self.mock_file.content_type = "application/pdf"
        self.mock_file.file = Mock()
        self.mock_file.size = 1024
    
    @pytest.mark.asyncio
    async def test_upload_rag_file_success(self):
        """Test successful RAG file upload"""
        tags = '["tag1", "tag2"]'
        
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class, \
             patch('app.api.routers.rag.s3_manager') as mock_s3_manager:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create.return_value = self.mock_document
            mock_s3_manager.put_object.return_value = None
            
            # Call function
            result = await upload_rag_file(
                self.mock_file, tags, self.mock_session, self.mock_user
            )
            
            # Assertions
            assert result.id == "doc123"
            assert result.name == "test.pdf"
            assert result.status == "uploaded"
            assert result.tags == ["tag1", "tag2"]
            
            # Verify calls
            mock_repo.create.assert_called_once()
            mock_s3_manager.put_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_rag_file_invalid_type(self):
        """Test upload with invalid file type"""
        self.mock_file.filename = "test.exe"
        tags = "[]"
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_rag_file(
                self.mock_file, tags, self.mock_session, self.mock_user
            )
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "file type" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_upload_rag_file_too_large(self):
        """Test upload with file too large"""
        self.mock_file.size = 100 * 1024 * 1024  # 100MB
        tags = "[]"
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_rag_file(
                self.mock_file, tags, self.mock_session, self.mock_user
            )
        
        assert exc_info.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert "too large" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_list_rag_documents_success(self):
        """Test successful RAG documents listing"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            
            # Mock session.query chain
            mock_query = Mock()
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 1
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [self.mock_document]
            self.mock_session.query.return_value = mock_query
            
            # Call function
            result = list_rag_documents(
                page=1, size=10, search="", status="",
                session=self.mock_session, current_user=self.mock_user
            )
            
            # Assertions
            assert result["total"] == 1
            assert result["page"] == 1
            assert result["size"] == 10
            assert result["pages"] == 1
            assert len(result["items"]) == 1
            assert result["items"][0].id == "doc123"
            
            # Verify calls
            mock_repo.get_all_paginated.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_rag_document_success(self):
        """Test successful get RAG document by ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            
            # Call function
            result = get_rag_document("doc123", session=self.mock_session, current_user=self.mock_user)
            
            # Assertions
            assert result["id"] == "doc123"
            assert result["name"] == "test.pdf"
            assert result["status"] == "processed"
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
    
    @pytest.mark.asyncio
    async def test_get_rag_document_not_found(self):
        """Test get RAG document with non-existent ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                get_rag_document("nonexistent", session=self.mock_session, current_user=self.mock_user)
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert exc_info.value.detail == "not_found"
    
    def test_update_rag_document_tags_success(self):
        """Test successful RAG document tags update"""
        tags_data = {"tags": ["newtag1", "newtag2"]}
        
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            mock_repo.update_tags.return_value = self.mock_document
            
            # Call function
            result = update_rag_document_tags(
                "doc123", tags_data["tags"], session=self.mock_session, current_user=self.mock_user
            )
            
            # Assertions
            assert result["id"] == "doc123"
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
    
    @pytest.mark.asyncio
    async def test_update_rag_document_tags_not_found(self):
        """Test update RAG document tags with non-existent ID"""
        tags_data = {"tags": ["newtag1", "newtag2"]}
        
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                update_rag_document_tags(
                    "nonexistent", tags_data, self.mock_session, self.mock_user
                )
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in exc_info.value.detail.lower()
    
    def test_search_rag_success(self):
        """Test successful RAG search"""
        with patch('app.api.routers.rag.RAGDocumentsService') as mock_service_class:
            # Setup mocks
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.search_documents.return_value = [self.mock_document]
            
            # Call function
            result = search_rag(
                query="test query", top_k=10, offset=0,
                session=self.mock_session, current_user={"id": "user123"}
            )
            
            # Assertions
            assert len(result["results"]) == 1
            assert result["results"][0]["id"] == "doc123"
            assert result["results"][0]["score"] == 0.95
            
            # Verify calls
            mock_service.search_documents.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_rag_file_success(self):
        """Test successful RAG file download"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class, \
             patch('app.api.routers.rag.s3_manager') as mock_s3_manager:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            mock_s3_manager.presign_get.return_value = "https://example.com/download"
            
            # Call function
            result = download_rag_file(
                "doc123", "original", self.mock_session, self.mock_user
            )
            
            # Assertions
            assert result["url"] == "https://example.com/download"
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
            mock_s3_manager.presign_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_rag_file_not_found(self):
        """Test download RAG file with non-existent ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                download_rag_file(
                    "nonexistent", "original", session=self.mock_session, current_user=self.mock_user
                )
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert exc_info.value.detail == "not_found"
    
    def test_get_rag_progress_success(self):
        """Test successful RAG progress retrieval"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            
            # Call function
            result = get_rag_progress("doc123", session=self.mock_session, current_user=self.mock_user)
            
            # Assertions
            assert result["status"] == "processed"
            assert result["progress"] == 100
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
    
    @pytest.mark.asyncio
    async def test_get_rag_progress_not_found(self):
        """Test get RAG progress with non-existent ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await get_rag_progress("nonexistent", self.mock_session, self.mock_user)
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in exc_info.value.detail.lower()
    
    def test_archive_rag_document_success(self):
        """Test successful RAG document archiving"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            mock_repo.archive_document.return_value = self.mock_document
            
            # Call function
            result = archive_rag_document("doc123", session=self.mock_session, current_user=self.mock_user)
            
            # Assertions
            assert result["id"] == "doc123"
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
    
    @pytest.mark.asyncio
    async def test_archive_rag_document_not_found(self):
        """Test archive RAG document with non-existent ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                archive_rag_document("nonexistent", session=self.mock_session, current_user=self.mock_user)
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert exc_info.value.detail == "not_found"
    
    def test_delete_rag_document_success(self):
        """Test successful RAG document deletion"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class, \
             patch('app.api.routers.rag.s3_manager') as mock_s3_manager:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_document
            mock_repo.delete_document.return_value = True
            mock_s3_manager.delete_object.return_value = None
            
            # Call function
            result = delete_rag_document("doc123", session=self.mock_session, current_user=self.mock_user)
            
            # Assertions
            assert result["deleted"] is True
            assert result["id"] == "doc123"
            
            # Verify calls
            mock_repo.get_by_id.assert_called_once_with("doc123")
    
    @pytest.mark.asyncio
    async def test_delete_rag_document_not_found(self):
        """Test delete RAG document with non-existent ID"""
        with patch('app.api.routers.rag.RAGDocumentsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                delete_rag_document("nonexistent", session=self.mock_session, current_user=self.mock_user)
            
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert exc_info.value.detail == "not_found"
