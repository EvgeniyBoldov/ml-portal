"""
Unit tests for analyze router
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException, UploadFile

from app.api.routers.analyze import _safe_ext, upload_analysis_file, list_analysis_documents, get_analysis_document, download_analysis_file
from app.models.analyze import AnalysisDocuments


class TestAnalyzeRouter:
    """Test analyze router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        
        # Mock analyze document
        self.mock_document = Mock(spec=AnalysisDocuments)
        self.mock_document.id = "doc123"
        self.mock_document.name = "test.pdf"
        self.mock_document.status = "processed"
        self.mock_document.url_file = "doc123/origin.pdf"
        self.mock_document.created_at = "2023-01-01T00:00:00"
        self.mock_document.updated_at = "2023-01-01T00:00:00"
        
        # Mock upload file
        self.mock_file = Mock(spec=UploadFile)
        self.mock_file.filename = "test.pdf"
        self.mock_file.content_type = "application/pdf"
        self.mock_file.file = Mock()
    
    def test_safe_ext_valid(self):
        """Test _safe_ext with valid filename"""
        result = _safe_ext("test.pdf")
        assert result == ".pdf"
    
    def test_safe_ext_docx(self):
        """Test _safe_ext with docx filename"""
        result = _safe_ext("document.docx")
        assert result == ".docx"
    
    def test_safe_ext_txt(self):
        """Test _safe_ext with txt filename"""
        result = _safe_ext("readme.txt")
        assert result == ".txt"
    
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
    
    def test_safe_ext_unsupported(self):
        """Test _safe_ext with unsupported extension"""
        result = _safe_ext("test.exe")
        assert result == ""
    
    def test_safe_ext_case_insensitive(self):
        """Test _safe_ext with uppercase extension"""
        result = _safe_ext("test.PDF")
        assert result == ".pdf"
    
    def test_safe_ext_multiple_dots(self):
        """Test _safe_ext with multiple dots"""
        result = _safe_ext("test.backup.pdf")
        assert result == ".pdf"
    
    @pytest.mark.asyncio
    async def test_upload_analysis_file_success(self):
        """Test successful analysis file upload"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class, \
             patch('app.api.routers.analyze.s3_manager') as mock_s3_manager, \
             patch('app.api.routers.analyze.upload_watch') as mock_upload_watch:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create_document.return_value = self.mock_document
            mock_s3_manager.put_object.return_value = None
            mock_upload_watch.return_value = None
            
            # Call function
            result = await upload_analysis_file(self.mock_file, self.mock_session)
            
            # Assertions
            assert result["id"] == "doc123"
            assert result["status"] == "uploaded"
            
            # Verify calls
            mock_repo.create_document.assert_called_once()
            mock_s3_manager.put_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_analysis_file_invalid_type(self):
        """Test upload with invalid file type"""
        self.mock_file.filename = "test.exe"
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_analysis_file(self.mock_file, self.mock_session)
        
        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_upload_analysis_file_no_filename(self):
        """Test upload with no filename"""
        self.mock_file.filename = None
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_analysis_file(self.mock_file, self.mock_session)
        
        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in exc_info.value.detail
    
    def test_list_analysis_documents_success(self):
        """Test successful analysis documents listing"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.list.return_value = [self.mock_document]
            
            # Call function
            result = list_analysis_documents(self.mock_session)
            
            # Assertions
            assert len(result["items"]) == 1
            assert result["items"][0]["id"] == "doc123"
            
            # Verify calls
            mock_repo.list.assert_called_once()
    
    def test_get_analysis_document_success(self):
        """Test successful get analysis document by ID"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_document
            
            # Call function
            result = get_analysis_document("doc123", self.mock_session)
            
            # Assertions
            assert result["id"] == "doc123"
            assert result["status"] == "processed"
            
            # Verify calls
            mock_repo.get.assert_called_once_with("doc123")
    
    def test_get_analysis_document_not_found(self):
        """Test get analysis document with non-existent ID"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                get_analysis_document("nonexistent", self.mock_session)
            
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()
    
    def test_download_analysis_file_success(self):
        """Test successful analysis file download"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class, \
             patch('app.api.routers.analyze.s3_manager') as mock_s3_manager, \
             patch('app.api.routers.analyze.settings') as mock_settings:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_document
            mock_s3_manager.presign_get.return_value = "https://example.com/download"
            mock_settings.S3_BUCKET_ANALYSIS = "test-bucket"
            
            # Call function
            result = download_analysis_file("doc123", self.mock_session)
            
            # Assertions
            assert result["url"] == "https://example.com/download"
            
            # Verify calls
            mock_repo.get.assert_called_once_with("doc123")
            mock_s3_manager.presign_get.assert_called_once()
    
    def test_download_analysis_file_not_found(self):
        """Test download analysis file with non-existent ID"""
        with patch('app.api.routers.analyze.AnalyzeRepo') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                download_analysis_file("nonexistent", self.mock_session)
            
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()
