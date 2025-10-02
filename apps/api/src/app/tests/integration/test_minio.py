"""
Интеграционные тесты для MinIO (S3).
Использует реальный MinIO для проверки загрузки, скачивания и управления файлами.
"""
import pytest
import asyncio
import io
import uuid
from datetime import datetime, timedelta
from minio import Minio
from minio.error import S3Error

from app.adapters.s3_client import s3_manager
from app.core.s3_links import S3LinkFactory


@pytest.mark.integration
class TestMinIOIntegration:
    """Интеграционные тесты для MinIO."""

    @pytest.mark.asyncio
    async def test_bucket_operations(self, minio_client, clean_minio):
        """Тест операций с bucket'ами."""
        bucket_name = "test-bucket-operations"
        
        # Create bucket
        minio_client.make_bucket(bucket_name)
        
        # Check if bucket exists
        buckets = minio_client.list_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        assert bucket_name in bucket_names
        
        # Remove bucket
        minio_client.remove_bucket(bucket_name)
        
        # Verify bucket is removed
        buckets = minio_client.list_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        assert bucket_name not in bucket_names

    @pytest.mark.asyncio
    async def test_file_upload_download(self, minio_client, clean_minio):
        """Тест загрузки и скачивания файлов."""
        bucket_name = "test-rag-documents"
        object_name = f"test-file-{uuid.uuid4()}.txt"
        test_content = "This is a test file content for MinIO integration testing."
        
        try:
            # Upload file
            file_data = io.BytesIO(test_content.encode('utf-8'))
            minio_client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # Verify file exists
            objects = list(minio_client.list_objects(bucket_name, prefix=object_name))
            assert len(objectobjects) == 1
            assert objects[0].object_name == object_name
            
            # Download file
            response = minio_client.get_object(bucket_name, object_name)
            downloaded_content = response.read().decode('utf-8')
            
            assert downloaded_content == test_content
            
        finally:
            # Cleanup
            try:
                minio_client.remove_object(bucket_name, object_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_presigned_urls(self, minio_client, clean_minio):
        """Тест генерации presigned URL'ов."""
        bucket_name = "test-rag-documents"
        object_name = f"presigned-test-{uuid.uuid4()}.txt"
        test_content = "Presigned URL test content"
        
        try:
            # Upload file first
            file_data = io.BytesIO(test_content.encode('utf-8'))
            minio_client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content)
            )
            
            # Generate presigned URL for download
            download_url = minio_client.presigned_get_object(
                bucket_name, 
                object_name, 
                expires=timedelta(hours=1)
            )
            
            assert download_url is not None
            assert "http" in download_url
            
            # Generate presigned URL for upload
            upload_url = minio_client.presigned_put_object(
                bucket_name, 
                f"upload-{object_name}", 
                expires=timedelta(hours=1)
            )
            
            assert upload_url is not None
            assert "http" in upload_url
            
        finally:
            # Cleanup
            try:
                minio_client.remove_object(bucket_name, object_name)
                minio_client.remove_object(bucket_name, f"upload-{object_name}")
            except:
                pass

    @pytest.mark.asyncio
    async def test_file_metadata(self, minio_client, clean_minio):
        """Тест работы с метаданными файлов."""
        bucket_name = "test-rag-documents"
        object_name = f"metadata-test-{uuid.uuid4()}.txt"
        test_content = "File with metadata"
        
        # Custom metadata
        metadata = {
            "content-type": "text/plain",
            "author": "integration-test",
            "created-at": datetime.now().isoformat(),
            "file-size": str(len(test_content))
        }
        
        try:
            # Upload file with metadata
            file_data = io.BytesIO(test_content.encode('utf-8'))
            minio_client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(test_content),
                metadata=metadata
            )
            
            # Get object info
            stat = minio_client.stat_object(bucket_name, object_name)
            
            assert stat.object_name == object_name
            assert stat.size == len(test_content)
            assert stat.metadata is not None
            
            # Check custom metadata
            for key, value in metadata.items():
                assert stat.metadata.get(key) == value
            
        finally:
            # Cleanup
            try:
                minio_client.remove_object(bucket_name, object_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_file_listing_and_filtering(self, minio_client, clean_minio):
        """Тест листинга и фильтрации файлов."""
        bucket_name = "test-rag-documents"
        prefix = f"listing-test-{uuid.uuid4()}"
        
        # Upload multiple files
        files_to_upload = [
            f"{prefix}/file1.txt",
            f"{prefix}/file2.pdf",
            f"{prefix}/subfolder/file3.txt",
            f"{prefix}/subfolder/file4.json"
        ]
        
        try:
            for file_path in files_to_upload:
                content = f"Content for {file_path}"
                file_data = io.BytesIO(content.encode('utf-8'))
                minio_client.put_object(
                    bucket_name, 
                    file_path, 
                    file_data, 
                    length=len(content)
                )
            
            # List all files with prefix
            objects = list(minio_client.list_objects(bucket_name, prefix=prefix))
            assert len(objects) == 4
            
            # List files in subfolder
            subfolder_objects = list(minio_client.list_objects(
                bucket_name, 
                prefix=f"{prefix}/subfolder/"
            ))
            assert len(subfolder_objects) == 2
            
            # List only .txt files
            txt_objects = []
            for obj in minio_client.list_objects(bucket_name, prefix=prefix):
                if obj.object_name.endswith('.txt'):
                    txt_objects.append(obj)
            
            assert len(txt_objects) == 2
            
        finally:
            # Cleanup
            for file_path in files_to_upload:
                try:
                    minio_client.remove_object(bucket_name, file_path)
                except:
                    pass

    @pytest.mark.asyncio
    async def test_s3_manager_integration(self, minio_client, clean_minio):
        """Тест интеграции с S3Manager."""
        bucket_name = "test-rag-documents"
        object_name = f"s3-manager-test-{uuid.uuid4()}.txt"
        test_content = "S3Manager integration test content"
        
        try:
            # Upload using S3Manager
            file_data = io.BytesIO(test_content.encode('utf-8'))
            result = await s3_manager.upload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=file_data,
                content_type="text/plain"
            )
            
            assert result is not None
            
            # Download using S3Manager
            downloaded_data = await s3_manager.download_file(
                bucket_name=bucket_name,
                object_name=object_name
            )
            
            downloaded_content = downloaded_data.read().decode('utf-8')
            assert downloaded_content == test_content
            
            # Generate presigned URL using S3Manager
            presigned_url = await s3_manager.generate_presigned_url(
                bucket_name=bucket_name,
                object_name=object_name,
                method="GET",
                expires_in=3600
            )
            
            assert presigned_url is not None
            assert "http" in presigned_url
            
        finally:
            # Cleanup
            try:
                await s3_manager.delete_file(bucket_name, object_name)
            except:
                pass

    @pytest.mark.asyncio
    async def test_s3_link_factory(self, minio_client, clean_minio):
        """Тест S3LinkFactory для генерации ссылок."""
        tenant_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        
        # Test document upload link
        upload_link = S3LinkFactory().for_document_upload(
            doc_id=doc_id,
            tenant_id=tenant_id,
            content_type="application/pdf"
        )
        
        assert upload_link.url is not None
        assert upload_link.bucket is not None
        assert upload_link.key is not None
        assert "http" in upload_link.url
        assert doc_id in upload_link.key
        
        # Test artifact link
        job_id = str(uuid.uuid4())
        filename = "test-artifact.json"
        
        artifact_link = S3LinkFactory().for_artifact(
            job_id=job_id,
            filename=filename,
            tenant_id=tenant_id
        )
        
        assert artifact_link.url is not None
        assert job_id in artifact_link.key
        assert filename in artifact_link.key

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self, minio_client, clean_minio):
        """Тест конкурентных загрузок."""
        bucket_name = "test-rag-documents"
        prefix = f"concurrent-{uuid.uuid4()}"
        
        async def upload_file(file_suffix: int):
            object_name = f"{prefix}/file_{file_suffix}.txt"
            content = f"Concurrent upload content {file_suffix}"
            file_data = io.BytesIO(content.encode('utf-8'))
            
            minio_client.put_object(
                bucket_name, 
                object_name, 
                file_data, 
                length=len(content)
            )
            return object_name
        
        try:
            # Execute concurrent uploads
            tasks = [upload_file(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 10
            
            # Verify all files were uploaded
            objects = list(minio_client.list_objects(bucket_name, prefix=prefix))
            assert len(objects) == 10
            
        finally:
            # Cleanup
            objects = list(minio_client.list_objects(bucket_name, prefix=prefix))
            for obj in objects:
                try:
                    minio_client.remove_object(bucket_name, obj.object_name)
                except:
                    pass

    @pytest.mark.asyncio
    async def test_error_handling(self, minio_client, clean_minio):
        """Тест обработки ошибок."""
        bucket_name = "non-existent-bucket"
        object_name = "non-existent-file.txt"
        
        # Test getting non-existent object
        with pytest.raises(S3Error):
            minio_client.get_object(bucket_name, object_name)
        
        # Test removing non-existent object
        with pytest.raises(S3Error):
            minio_client.remove_object(bucket_name, object_name)
        
        # Test accessing non-existent bucket
        with pytest.raises(S3Error):
            minio_client.list_objects(bucket_name)
