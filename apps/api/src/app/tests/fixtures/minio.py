"""
Фикстуры для работы с MinIO в тестах.
"""
import pytest
from minio import Minio
from app.core.config import get_settings


@pytest.fixture
def minio_client():
    """Создает MinIO клиент для тестов."""
    settings = get_settings()
    endpoint = settings.S3_ENDPOINT.replace("http://", "").replace("https://", "")
    
    client = Minio(
        endpoint,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        secure=settings.S3_SECURE
    )
    
    return client


@pytest.fixture
def clean_minio(minio_client):
    """Очищает MinIO перед тестом."""
    # Удаляем тестовые bucket'ы если они существуют
    test_buckets = ["test-rag-documents", "test-artifacts"]
    
    for bucket in test_buckets:
        try:
            if minio_client.bucket_exists(bucket):
                # Удаляем все объекты в bucket
                objects = minio_client.list_objects(bucket, recursive=True)
                for obj in objects:
                    minio_client.remove_object(bucket, obj.object_name)
                # Удаляем bucket
                minio_client.remove_bucket(bucket)
        except Exception:
            pass
    
    # Создаем тестовые bucket'ы
    for bucket in test_buckets:
        try:
            if not minio_client.bucket_exists(bucket):
                minio_client.make_bucket(bucket)
        except Exception:
            pass
    
    yield minio_client
    
    # Cleanup после теста
    for bucket in test_buckets:
        try:
            if minio_client.bucket_exists(bucket):
                # Удаляем все объекты в bucket
                objects = minio_client.list_objects(bucket, recursive=True)
                for obj in objects:
                    minio_client.remove_object(bucket, obj.object_name)
                # Удаляем bucket
                minio_client.remove_bucket(bucket)
        except Exception:
            pass
