"""
Unit tests for S3 core components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.s3 import S3Manager


class TestS3Manager:
    """Test S3Manager"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_client = Mock()
        self.s3_manager = S3Manager()
    
    @patch.object(S3Manager, '_get_client')
    def test_health_check(self, mock_get_client):
        """Test S3 health check"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.list_buckets.return_value = {'Buckets': []}
        
        result = self.s3_manager.health_check()
        assert result is True
    
    @patch.object(S3Manager, '_get_client')
    def test_health_check_failure(self, mock_get_client):
        """Test S3 health check failure"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.list_buckets.side_effect = Exception("S3 error")
        
        result = self.s3_manager.health_check()
        assert result is False
    
    @patch.object(S3Manager, '_get_client')
    def test_ensure_bucket(self, mock_get_client):
        """Test ensuring bucket exists"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.bucket_exists.return_value = True
        
        result = self.s3_manager.ensure_bucket("test-bucket")
        assert result is True
    
    @patch.object(S3Manager, '_get_client')
    def test_ensure_bucket_create(self, mock_get_client):
        """Test creating bucket if it doesn't exist"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.bucket_exists.return_value = False
        self.mock_client.make_bucket.return_value = {}
        
        result = self.s3_manager.ensure_bucket("test-bucket")
        assert result is True
        self.mock_client.make_bucket.assert_called_once()
    
    @patch.object(S3Manager, '_get_client')
    def test_list_buckets(self, mock_get_client):
        """Test listing buckets"""
        mock_get_client.return_value = self.mock_client
        
        # Mock MinIO bucket objects
        mock_bucket1 = Mock()
        mock_bucket1.name = 'bucket1'
        mock_bucket1.creation_date = '2024-01-01'
        mock_bucket2 = Mock()
        mock_bucket2.name = 'bucket2'
        mock_bucket2.creation_date = '2024-01-02'
        
        self.mock_client.list_buckets.return_value = [mock_bucket1, mock_bucket2]
        
        result = self.s3_manager.list_buckets()
        expected = [
            {'name': 'bucket1', 'creation_date': '2024-01-01'},
            {'name': 'bucket2', 'creation_date': '2024-01-02'}
        ]
        assert result == expected
    
    @patch.object(S3Manager, '_get_client')
    def test_put_object(self, mock_get_client):
        """Test putting object to S3"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.put_object.return_value = {'ETag': '"test-etag"'}
        
        result = self.s3_manager.put_object(
            bucket="test-bucket",
            key="test-key",
            data=b"test data",
            content_type="text/plain"
        )
        assert result is True
    
    @patch.object(S3Manager, '_get_client')
    def test_get_object(self, mock_get_client):
        """Test getting object from S3"""
        mock_get_client.return_value = self.mock_client
        mock_response = Mock()
        self.mock_client.get_object.return_value = mock_response
        
        result = self.s3_manager.get_object("test-bucket", "test-key")
        assert result == mock_response
    
    @patch.object(S3Manager, '_get_client')
    def test_get_object_not_found(self, mock_get_client):
        """Test getting non-existent object"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.get_object.side_effect = Exception("Not found")
        
        result = self.s3_manager.get_object("test-bucket", "test-key")
        assert result is None
    
    @patch.object(S3Manager, '_get_client')
    def test_delete_object(self, mock_get_client):
        """Test deleting object from S3"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.remove_object.return_value = {}
        
        result = self.s3_manager.delete_object("test-bucket", "test-key")
        assert result is True
    
    @patch.object(S3Manager, '_get_client')
    def test_delete_object_failure(self, mock_get_client):
        """Test deleting object failure"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.remove_object.side_effect = Exception("Delete failed")
        
        result = self.s3_manager.delete_object("test-bucket", "test-key")
        assert result is False
    
    @patch.object(S3Manager, '_get_client')
    def test_stat_object(self, mock_get_client):
        """Test getting object stats"""
        mock_get_client.return_value = self.mock_client
        
        # Mock MinIO stat object
        mock_stat = Mock()
        mock_stat.size = 1024
        mock_stat.etag = 'test-etag'
        mock_stat.last_modified = '2024-01-01T00:00:00Z'
        mock_stat.content_type = 'text/plain'
        mock_stat.metadata = {}
        
        self.mock_client.stat_object.return_value = mock_stat
        
        result = self.s3_manager.stat_object("test-bucket", "test-key")
        expected = {
            'size': 1024,
            'etag': 'test-etag',
            'last_modified': '2024-01-01T00:00:00Z',
            'content_type': 'text/plain',
            'metadata': {}
        }
        assert result == expected
    
    def test_stat_object_not_found(self):
        """Test getting stats for non-existent object"""
        self.mock_client.head_object.side_effect = Exception("Not found")
        
        result = self.s3_manager.stat_object("test-bucket", "test-key")
        assert result is None
    
    @patch.object(S3Manager, '_get_client')
    def test_presign_put(self, mock_get_client):
        """Test generating presigned PUT URL"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.presigned_put_object.return_value = "https://presigned-url.com"
        
        result = self.s3_manager.presign_put("test-bucket", "test-key")
        assert result == "https://presigned-url.com"
    
    @patch.object(S3Manager, '_get_client')
    def test_presign_get(self, mock_get_client):
        """Test generating presigned GET URL"""
        mock_get_client.return_value = self.mock_client
        self.mock_client.presigned_get_object.return_value = "https://presigned-url.com"
        
        result = self.s3_manager.presign_get("test-bucket", "test-key")
        assert result == "https://presigned-url.com"
    
    @patch.object(S3Manager, '_get_client')
    def test_list_objects(self, mock_get_client):
        """Test listing objects in bucket"""
        mock_get_client.return_value = self.mock_client
        
        # Mock MinIO object objects
        mock_obj1 = Mock()
        mock_obj1.object_name = 'file1.txt'
        mock_obj1.size = 1024
        mock_obj1.etag = 'etag1'
        mock_obj1.last_modified = '2024-01-01T00:00:00Z'
        mock_obj1.is_dir = False
        
        mock_obj2 = Mock()
        mock_obj2.object_name = 'file2.txt'
        mock_obj2.size = 2048
        mock_obj2.etag = 'etag2'
        mock_obj2.last_modified = '2024-01-02T00:00:00Z'
        mock_obj2.is_dir = False
        
        self.mock_client.list_objects.return_value = [mock_obj1, mock_obj2]
        
        result = self.s3_manager.list_objects("test-bucket", "prefix/")
        expected = [
            {
                'key': 'file1.txt',
                'size': 1024,
                'etag': 'etag1',
                'last_modified': '2024-01-01T00:00:00Z',
                'is_dir': False
            },
            {
                'key': 'file2.txt',
                'size': 2048,
                'etag': 'etag2',
                'last_modified': '2024-01-02T00:00:00Z',
                'is_dir': False
            }
        ]
        assert result == expected
    
    def test_list_objects_empty(self):
        """Test listing objects in empty bucket"""
        self.mock_client.list_objects_v2.return_value = {}
        
        result = self.s3_manager.list_objects("test-bucket")
        assert result == []
