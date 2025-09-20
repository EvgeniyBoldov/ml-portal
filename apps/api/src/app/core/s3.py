from __future__ import annotations
from typing import BinaryIO, Optional, List, Dict, Any, Union
from urllib.parse import urlparse
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from .config import settings
from .logging import get_logger

logger = get_logger(__name__)

class S3Manager:
    """S3/MinIO client manager with enhanced functionality"""
    
    def __init__(self):
        self._client: Optional[Minio] = None
        self._endpoint = settings.S3_ENDPOINT
        self._public_endpoint = settings.S3_PUBLIC_ENDPOINT
        self._access_key = settings.S3_ACCESS_KEY
        self._secret_key = settings.S3_SECRET_KEY
        self._secure = False
        self._netloc = self._endpoint
        
        # Parse endpoint for secure connection
        if self._endpoint.startswith("http://") or self._endpoint.startswith("https://"):
            u = urlparse(self._endpoint)
            self._secure = (u.scheme == "https")
            self._netloc = u.netloc
    
    def _get_client(self) -> Minio:
        """Get or create MinIO client"""
        if self._client is None:
            self._client = Minio(
                self._netloc,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
        return self._client
    
    def reset_client(self) -> None:
        """Reset client connection"""
        self._client = None
        logger.info("S3 client reset")
    
    def health_check(self) -> bool:
        """Check S3 connection health"""
        try:
            client = self._get_client()
            client.list_buckets()
            return True
        except Exception as e:
            logger.error(f"S3 health check failed: {e}")
            return False
    
    def ensure_bucket(self, bucket: str) -> bool:
        """Ensure bucket exists, create if not"""
        try:
            client = self._get_client()
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                logger.info(f"Created bucket: {bucket}")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure bucket {bucket}: {e}")
            return False
    
    def list_buckets(self) -> List[Dict[str, Any]]:
        """List all buckets"""
        try:
            client = self._get_client()
            buckets = client.list_buckets()
            return [{"name": bucket.name, "creation_date": bucket.creation_date} for bucket in buckets]
        except Exception as e:
            logger.error(f"Failed to list buckets: {e}")
            return []
    
    def put_object(self, bucket: str, key: str, data: Union[bytes, BinaryIO], 
                   length: Optional[int] = None, content_type: Optional[str] = None) -> bool:
        """Upload object to S3"""
        try:
            client = self._get_client()
            self.ensure_bucket(bucket)
            
            if hasattr(data, "read"):
                result = client.put_object(bucket, key, data, length=length or -1, content_type=content_type)
            else:
                import io
                bio = io.BytesIO(data if isinstance(data, (bytes, bytearray)) else bytes(data))
                result = client.put_object(bucket, key, bio, length=len(bio.getvalue()), content_type=content_type)
            
            logger.info(f"Uploaded object: {bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload object {bucket}/{key}: {e}")
            return False
    
    def get_object(self, bucket: str, key: str) -> Optional[BinaryIO]:
        """Download object from S3"""
        try:
            client = self._get_client()
            return client.get_object(bucket, key)
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"Object not found: {bucket}/{key}")
                return None
            logger.error(f"Failed to get object {bucket}/{key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get object {bucket}/{key}: {e}")
            return None
    
    def delete_object(self, bucket: str, key: str) -> bool:
        """Delete object from S3"""
        try:
            client = self._get_client()
            client.remove_object(bucket, key)
            logger.info(f"Deleted object: {bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete object {bucket}/{key}: {e}")
            return False
    
    def stat_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata"""
        try:
            client = self._get_client()
            stat = client.stat_object(bucket, key)
            return {
                "size": stat.size,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
                "content_type": stat.content_type,
                "metadata": stat.metadata
            }
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            logger.error(f"Failed to stat object {bucket}/{key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to stat object {bucket}/{key}: {e}")
            return None
    
    def presign_put(self, bucket: str, key: str, expiry_seconds: int = 3600) -> Optional[str]:
        """Generate presigned URL for PUT operation"""
        try:
            client = self._get_client()
            url = client.presigned_put_object(bucket, key, expires=timedelta(seconds=expiry_seconds))
            
            # Replace internal endpoint with public endpoint for external access
            if self._public_endpoint != self._endpoint:
                internal_base = self._endpoint.rstrip('/')
                public_base = self._public_endpoint.rstrip('/')
                url = url.replace(internal_base, public_base)
            
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned PUT URL for {bucket}/{key}: {e}")
            return None
    
    def presign_get(self, bucket: str, key: str, expiry_seconds: int = 3600) -> Optional[str]:
        """Generate presigned URL for GET operation"""
        try:
            client = self._get_client()
            url = client.presigned_get_object(bucket, key, expires=timedelta(seconds=expiry_seconds))
            
            # Replace internal endpoint with public endpoint for external access
            if self._public_endpoint != self._endpoint:
                internal_base = self._endpoint.rstrip('/')
                public_base = self._public_endpoint.rstrip('/')
                url = url.replace(internal_base, public_base)
            
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned GET URL for {bucket}/{key}: {e}")
            return None
    
    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True) -> List[Dict[str, Any]]:
        """List objects in bucket"""
        try:
            client = self._get_client()
            objects = client.list_objects(bucket, prefix=prefix, recursive=recursive)
            return [{
                "key": obj.object_name,
                "size": obj.size,
                "etag": obj.etag,
                "last_modified": obj.last_modified,
                "is_dir": obj.is_dir
            } for obj in objects]
        except Exception as e:
            logger.error(f"Failed to list objects in {bucket}: {e}")
            return []

# Global S3 manager instance
s3_manager = S3Manager()

# Convenience functions for backward compatibility
def get_minio() -> Minio:
    """Get MinIO client (backward compatibility)"""
    return s3_manager._get_client()

def reset_client():
    """Reset S3 client (backward compatibility)"""
    s3_manager.reset_client()

def ensure_bucket(bucket: str) -> None:
    """Ensure bucket exists (backward compatibility)"""
    s3_manager.ensure_bucket(bucket)

def put_object(bucket: str, key: str, data: Union[bytes, BinaryIO], 
               length: Optional[int] = None, content_type: Optional[str] = None):
    """Upload object (backward compatibility)"""
    return s3_manager.put_object(bucket, key, data, length, content_type)

def get_object(bucket: str, key: str):
    """Download object (backward compatibility)"""
    return s3_manager.get_object(bucket, key)

def stat_object(bucket: str, key: str):
    """Get object metadata (backward compatibility)"""
    return s3_manager.stat_object(bucket, key)

def list_buckets():
    """List buckets (backward compatibility)"""
    return s3_manager.list_buckets()

def presign_put(bucket: str, key: str, expiry_seconds: int = 3600) -> str:
    """Generate presigned PUT URL (backward compatibility)"""
    return s3_manager.presign_put(bucket, key, expiry_seconds) or ""