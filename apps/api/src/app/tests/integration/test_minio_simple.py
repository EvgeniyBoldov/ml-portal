"""
Простые интеграционные тесты для MinIO (S3).
Использует реальный MinIO для проверки базовых операций.
"""
import pytest
import asyncio
import io
import uuid
from minio import Minio
from minio.error import S3Error


@pytest.mark.integration
class TestMinIOIntegration:
    """Интеграционные тесты для MinIO."""

    @pytest.mark.asyncio
    async def test_minio_connection(self):
        """Тест подключения к MinIO."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        # Test connection by listing buckets
        buckets = client.list_buckets()
        assert buckets is not None

    @pytest.mark.asyncio
    async def test_bucket_operations(self):
        """Тест операций с bucket'ами."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = "test-bucket-operations"
        
        try:
            # Create bucket
            client.make_bucket(bucket_name)
            
            # Check if bucket exists
            buckets = client.list_buckets()
            bucket_names = [bucket.name for bucket in buckets]
            assert bucket_name in bucket_names
            
            # Remove bucket
            client.remove_bucket(bucket_name)
            
            # Verify bucket is removed
            buckets = client.list_buckets()
            bucket_names = [bucket.name for bucket in buckets]
            assert bucket_name not in bucket_names
            
        except Exception as e:
            # Cleanup in case of error
            try:
                client.remove_bucket(bucket_name)
            except:
                pass
            raise e

    @pytest.mark.asyncio
    async def test_file_upload_head_get_delete_happy_path(self):
        """Тест полного цикла: upload → head → get → delete."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = "test-rag-documents"
        object_name = f"happy-path-{uuid.uuid4()}.txt"
        test_content = "This is a test file content for MinIO integration testing."
        
        try:
            # Ensure bucket exists
            try:
                client.make_bucket(bucket_name)
            except:
                pass  # Bucket might already exist
            
            # 1. Upload file
            file_data = io.BytesIO(test_content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # 2. Head (get metadata) - verify file exists and get info
            stat = client.stat_object(bucket_name, object_name)
            assert stat.object_name == object_name
            assert stat.size == len(test_content)
            assert stat.last_modified is not None
            
            # 3. Get (download) file
            response = client.get_object(bucket_name, object_name)
            downloaded_content = response.read().decode('utf-8')
            assert downloaded_content == test_content
            
            # 4. Verify file exists in listing
            objects = list(client.list_objects(bucket_name, prefix=object_name))
            assert len(objects) == 1
            assert objects[0].object_name == object_name
            
            # 5. Delete file
            client.remove_object(bucket_name, object_name)
            
            # 6. Verify file is deleted
            objects_after_delete = list(client.list_objects(bucket_name, prefix=object_name))
            assert len(objects_after_delete) == 0
            
            # 7. Verify head fails after delete
            with pytest.raises(S3Error):
                client.stat_object(bucket_name, object_name)
            
        finally:
            # Cleanup in case of error
            try:
                client.remove_object(bucket_name, object_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_presigned_urls(self):
        """Тест генерации presigned URL'ов."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = "test-rag-documents"
        object_name = f"presigned-test-{uuid.uuid4()}.txt"
        test_content = "Presigned URL test content"
        
        try:
            # Ensure bucket exists
            try:
                client.make_bucket(bucket_name)
            except:
                pass  # Bucket might already exist
            
            # Upload file first
            file_data = io.BytesIO(test_content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # Generate presigned URL for download
            from datetime import timedelta
            download_url = client.presigned_get_object(
                bucket_name, 
                object_name, 
                expires=timedelta(hours=1)
            )
            
            assert download_url is not None
            assert "http" in download_url
            
            # Generate presigned URL for upload
            upload_url = client.presigned_put_object(
                bucket_name, 
                f"upload-{object_name}", 
                expires=timedelta(hours=1)
            )
            
            assert upload_url is not None
            assert "http" in upload_url
            
        finally:
            # Cleanup
            try:
                client.remove_object(bucket_name, object_name)
                client.remove_object(bucket_name, f"upload-{object_name}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_file_metadata(self):
        """Тест работы с метаданными файлов."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = f"test-metadata-{uuid.uuid4()}"
        object_name = f"metadata-test-{uuid.uuid4()}.txt"
        test_content = "File with metadata"
        
        try:
            # Create bucket
            client.make_bucket(bucket_name)
            
            # Upload file with metadata
            file_data = io.BytesIO(test_content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # Get object info
            stat = client.stat_object(bucket_name, object_name)
            
            assert stat.object_name == object_name
            assert stat.size == len(test_content)
            assert stat.last_modified is not None
            
        finally:
            # Cleanup
            try:
                client.remove_object(bucket_name, object_name)
                client.remove_bucket(bucket_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_file_listing_and_filtering(self):
        """Тест листинга и фильтрации файлов."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = f"test-listing-{uuid.uuid4()}"
        object_name = f"file-{uuid.uuid4()}.txt"
        
        try:
            # Create bucket
            client.make_bucket(bucket_name)
            
            # Upload single file
            content = f"Content for {object_name}"
            file_data = io.BytesIO(content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(content)
            )
            
            # List all files
            objects = list(client.list_objects(bucket_name))
            assert len(objects) == 1
            assert objects[0].object_name == object_name
            
        finally:
            # Cleanup
            try:
                client.remove_object(bucket_name, object_name)
                client.remove_bucket(bucket_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Тест обработки ошибок."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = f"test-error-{uuid.uuid4()}"
        object_name = "non-existent-file.txt"
        
        try:
            # Create bucket
            client.make_bucket(bucket_name)
            
            # Test getting non-existent object
            with pytest.raises(S3Error):
                client.get_object(bucket_name, object_name)
            
            # Test removing non-existent object (this should not raise error)
            client.remove_object(bucket_name, object_name)
            
        finally:
            # Cleanup
            try:
                client.remove_bucket(bucket_name)
            except:
                pass
