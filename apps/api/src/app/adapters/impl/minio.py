"""
MinIO client for presigned URL generation
"""
import os
from datetime import timedelta
from urllib.parse import urlparse, urlunparse
from typing import Optional

from minio import Minio
from minio.error import S3Error

# Environment variables
PUBLIC_FILES_HOST = os.getenv("PUBLIC_FILES_HOST", "files.localhost")
MINIO_ENDPOINT_INTERNAL = os.getenv("MINIO_ENDPOINT_INTERNAL", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
PRESIGNED_TTL_SECONDS = int(os.getenv("PRESIGNED_TTL_SECONDS", "60"))

# Initialize MinIO client
_minio_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    """Get MinIO client instance"""
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            MINIO_ENDPOINT_INTERNAL,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
    return _minio_client


def presign_get(bucket: str, key: str, expires_sec: int = PRESIGNED_TTL_SECONDS) -> str:
    """
    Generate presigned GET URL for MinIO object
    
    Args:
        bucket: MinIO bucket name
        key: Object key in bucket
        expires_sec: URL expiration time in seconds
        
    Returns:
        Presigned URL with public host
        
    Raises:
        S3Error: If presigned URL generation fails
    """
    try:
        # Create a temporary client with internal MinIO endpoint
        from minio import Minio
        
        # Parse the internal MinIO endpoint
        internal_endpoint = MINIO_ENDPOINT_INTERNAL.replace("http://", "").replace("https://", "")
        
        # Create client for internal MinIO
        client = Minio(
            internal_endpoint,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        
        # Generate presigned URL for internal MinIO
        url = client.presigned_get_object(
            bucket, 
            key, 
            expires=timedelta(seconds=expires_sec)
        )
        
        # Replace scheme and port only, keep minio:9000 as host for signature validation
        # Nginx will proxy minio:9000 to actual MinIO instance
        from urllib.parse import urlparse, urlunparse
        parts = urlparse(url)
        # Use HTTPS for public access but keep minio:9000 as host
        new_parts = parts._replace(scheme="https", netloc=f"{PUBLIC_FILES_HOST}:8443")
        new_url = urlunparse(new_parts)
        
        # MinIO expects the Host header to match the signature
        # So we return URL that will be accessed through nginx proxy
        # But nginx will set Host: minio:9000 to match the signature
        return new_url
        
    except S3Error as e:
        raise S3Error(f"Failed to generate presigned URL for {bucket}/{key}: {str(e)}")


def check_object_exists(bucket: str, key: str) -> bool:
    """
    Check if object exists in MinIO
    
    Args:
        bucket: MinIO bucket name
        key: Object key in bucket
        
    Returns:
        True if object exists, False otherwise
    """
    try:
        client = get_minio_client()
        client.stat_object(bucket, key)
        return True
    except S3Error:
        return False


def get_object_info(bucket: str, key: str) -> dict:
    """
    Get object metadata from MinIO
    
    Args:
        bucket: MinIO bucket name
        key: Object key in bucket
        
    Returns:
        Dictionary with object metadata
        
    Raises:
        S3Error: If object doesn't exist or access fails
    """
    try:
        client = get_minio_client()
        stat = client.stat_object(bucket, key)
        
        return {
            "size": stat.size,
            "etag": stat.etag,
            "content_type": stat.content_type,
            "last_modified": stat.last_modified,
            "metadata": stat.metadata
        }
    except S3Error as e:
        raise S3Error(f"Failed to get object info for {bucket}/{key}: {str(e)}")

