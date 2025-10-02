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
    async def test_file_upload_download(self):
        """Тест загрузки и скачивания файлов."""
        client = Minio(
            "minio-test:9000",
            access_key="testadmin",
            secret_key="testadmin123",
            secure=False
        )
        
        bucket_name = "test-rag-documents"
        object_name = f"test-file-{uuid.uuid4()}.txt"
        test_content = "This is a test file content for MinIO integration testing."
        
        try:
            # Ensure bucket exists
            try:
                client.make_bucket(bucket_name)
            except:
                pass  # Bucket might already exist
            
            # Upload file
            file_data = io.BytesIO(test_content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # Verify file exists
            objects = list(client.list_objects(bucket_name, prefix=object_name))
            assert len(objects) == 1
            assert objects[0].object_name == object_name
            
            # Download file
            response = client.get_object(bucket_name, object_name)
            downloaded_content = response.read().decode('utf-8')
            
            assert downloaded_content == test_content
            
        finally:
            # Cleanup
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
        
        bucket_name = "test-rag-documents"
        object_name = f"metadata-test-{uuid.uuid4()}.txt"
        test_content = "File with metadata"
        
        # Custom metadata
        metadata = {
            "content-type": "text/plain",
            "author": "integration-test",
            "file-size": str(len(test_content))
        }
        
        try:
            # Ensure bucket exists
            try:
                client.make_bucket(bucket_name)
            except:
                pass  # Bucket might already exist
            
            # Upload file with metadata
            file_data = io.BytesIO(test_content.encode('utf-8'))
            client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content),
                metadata=metadata
            )
            
            # Get object info
            stat = client.stat_object(bucket_name, object_name)
            
            assert stat.object_name == object_name
            assert stat.size == len(test_content)
            assert stat.metadata is not None
            
            # Check custom metadata
            for key, value in metadata.items():
                assert stat.metadata.get(key) == value
            
        finally:
            # Cleanup
            try:
                client.remove_object(bucket_name, object_name)
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
        
        bucket_name = "test-rag-documents"
        prefix = f"listing-test-{uuid.uuid4()}"
        
        try:
            # Ensure bucket exists
            try:
                client.make_bucket(bucket_name)
            except:
                pass  # Bucket might already exist
            
            # Upload multiple files
            files_to_upload = [
                f"{prefix}/file1.txt",
                f"{prefix}/file2.pdf",
                f"{prefix}/subfolder/file3.txt",
                f"{prefix}/subfolder/file4.json"
            ]
            
            for file_path in files_to_upload:
                content = f"Content for {file_path}"
                file_data = io.BytesIO(content.encode('utf-8'))
                client.put_object(
                    bucket_name, 
                    file_path, 
                    file_data, 
                    length=len(content)
                )
            
            # List all files with prefix
            objects = list(client.list_objects(bucket_name, prefix=prefix))
            assert len(objects) == 4
            
            # List files in subfolder
            subfolder_objects = list(client.list_objects(
                bucket_name, 
                prefix=f"{prefix}/subfolder/"
            ))
            assert len(subfolder_objects) == 2
            
            # List only .txt files
            txt_objects = []
            for obj in client.list_objects(bucket_name, prefix=prefix):
                if obj.object_name.endswith('.txt'):
                    txt_objects.append(obj)
            
            assert len(txt_objects) == 2
            
        finally:
            # Cleanup
            for file_path in files_to_upload:
                try:
                    client.remove_object(bucket_name, file_path)
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
        
        bucket_name = "non-existent-bucket"
        object_name = "non-existent-file.txt"
        
        # Test getting non-existent object
        with pytest.raises(S3Error):
            client.get_object(bucket_name, object_name)
        
        # Test removing non-existent object
        with pytest.raises(S3Error):
            client.remove_object(bucket_name, object_name)
        
        # Test accessing non-existent bucket
        with pytest.raises(S3Error):
            client.list_objects(bucket_name)
