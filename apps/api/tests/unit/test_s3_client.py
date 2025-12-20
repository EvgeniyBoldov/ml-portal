"""
Unit tests for S3Client - presigned URL generation with public endpoint replacement
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.adapters.s3_client import S3Client, PresignOptions


class TestS3ClientPresignedUrl:
    """Test S3Client.generate_presigned_url with public endpoint replacement"""
    
    @pytest.fixture
    def mock_settings_with_public(self):
        """Settings with S3_PUBLIC_ENDPOINT configured"""
        settings = MagicMock()
        settings.S3_ENDPOINT = "http://minio:9000"
        settings.S3_PUBLIC_ENDPOINT = "https://files.localhost:8443"
        settings.S3_ACCESS_KEY = "minioadmin"
        settings.S3_SECRET_KEY = "minioadmin123"
        settings.S3_SECURE = False
        return settings
    
    @pytest.fixture
    def mock_settings_without_public(self):
        """Settings without S3_PUBLIC_ENDPOINT (None)"""
        settings = MagicMock()
        settings.S3_ENDPOINT = "http://minio:9000"
        settings.S3_PUBLIC_ENDPOINT = None
        settings.S3_ACCESS_KEY = "minioadmin"
        settings.S3_SECRET_KEY = "minioadmin123"
        settings.S3_SECURE = False
        return settings
    
    @pytest.mark.asyncio
    async def test_presigned_url_replaces_internal_with_public(self, mock_settings_with_public):
        """When S3_PUBLIC_ENDPOINT is set, URL should use public endpoint"""
        with patch('app.adapters.s3_client.get_settings', return_value=mock_settings_with_public):
            client = S3Client()
            client._settings = mock_settings_with_public
            
            # Mock boto3 client
            mock_boto_client = MagicMock()
            mock_boto_client.generate_presigned_url = MagicMock(
                return_value="http://minio:9000/rag/tenant123/doc456/file.pdf?X-Amz-Signature=abc123"
            )
            client.client = mock_boto_client
            
            url = await client.generate_presigned_url(
                bucket="rag",
                key="tenant123/doc456/file.pdf",
                options=PresignOptions(method="GET", expires_in=3600)
            )
            
            # URL should have public endpoint
            assert url.startswith("https://files.localhost:8443/")
            assert "X-Amz-Signature=abc123" in url
            assert "minio:9000" not in url
    
    @pytest.mark.asyncio
    async def test_presigned_url_keeps_internal_when_no_public(self, mock_settings_without_public):
        """When S3_PUBLIC_ENDPOINT is None, URL should keep internal endpoint"""
        with patch('app.adapters.s3_client.get_settings', return_value=mock_settings_without_public):
            client = S3Client()
            client._settings = mock_settings_without_public
            
            # Mock boto3 client
            mock_boto_client = MagicMock()
            mock_boto_client.generate_presigned_url = MagicMock(
                return_value="http://minio:9000/rag/tenant123/doc456/file.pdf?X-Amz-Signature=abc123"
            )
            client.client = mock_boto_client
            
            url = await client.generate_presigned_url(
                bucket="rag",
                key="tenant123/doc456/file.pdf",
                options=PresignOptions(method="GET", expires_in=3600)
            )
            
            # URL should keep internal endpoint
            assert url.startswith("http://minio:9000/")
            assert "X-Amz-Signature=abc123" in url
    
    @pytest.mark.asyncio
    async def test_presigned_url_preserves_path_and_query(self, mock_settings_with_public):
        """URL replacement should preserve path and query parameters"""
        with patch('app.adapters.s3_client.get_settings', return_value=mock_settings_with_public):
            client = S3Client()
            client._settings = mock_settings_with_public
            
            # Mock boto3 client with complex URL
            internal_url = (
                "http://minio:9000/rag/tenant-uuid/doc-uuid/canonical/checksum_v1.jsonl"
                "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
                "&X-Amz-Credential=minioadmin%2F20231220%2Fus-east-1%2Fs3%2Faws4_request"
                "&X-Amz-Date=20231220T120000Z"
                "&X-Amz-Expires=3600"
                "&X-Amz-SignedHeaders=host"
                "&X-Amz-Signature=abc123def456"
            )
            mock_boto_client = MagicMock()
            mock_boto_client.generate_presigned_url = MagicMock(return_value=internal_url)
            client.client = mock_boto_client
            
            url = await client.generate_presigned_url(
                bucket="rag",
                key="tenant-uuid/doc-uuid/canonical/checksum_v1.jsonl"
            )
            
            # Should have public scheme and host
            assert url.startswith("https://files.localhost:8443/")
            
            # Should preserve path
            assert "/rag/tenant-uuid/doc-uuid/canonical/checksum_v1.jsonl" in url
            
            # Should preserve all query params
            assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
            assert "X-Amz-Signature=abc123def456" in url
            assert "X-Amz-Expires=3600" in url


class TestPresignOptions:
    """Test PresignOptions dataclass"""
    
    def test_default_values(self):
        """Default options should have sensible values"""
        opts = PresignOptions()
        
        assert opts.expires_in == 3600
        assert opts.method == "GET"
        assert opts.content_type is None
        assert opts.response_headers is None
    
    def test_custom_values(self):
        """Should accept custom values"""
        opts = PresignOptions(
            expires_in=7200,
            method="PUT",
            content_type="application/pdf",
            response_headers={"Content-Disposition": "attachment; filename=doc.pdf"}
        )
        
        assert opts.expires_in == 7200
        assert opts.method == "PUT"
        assert opts.content_type == "application/pdf"
        assert opts.response_headers["Content-Disposition"] == "attachment; filename=doc.pdf"
