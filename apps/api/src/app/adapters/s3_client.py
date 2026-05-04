"""
S3/MinIO adapter with proper error handling and timeouts
"""
from __future__ import annotations
import asyncio
from app.core.logging import get_logger
from dataclasses import dataclass
from typing import Optional, Dict, Any, BinaryIO
from botocore.exceptions import ClientError, NoCredentialsError
import boto3
from botocore.config import Config
from app.core.config import get_settings

logger = get_logger(__name__)


class S3Client:
    """S3/MinIO client with proper configuration and error handling"""
    
    def __init__(self):
        self.client: Optional[Any] = None
        self._settings = get_settings()
    
    def _get_client(self):
        """Get configured S3 client"""
        if self.client is None:
            config = Config(
                read_timeout=60,
                connect_timeout=60,
                retries={'max_attempts': 3, 'mode': 'adaptive'}
            )
            
            # Ensure endpoint has protocol
            endpoint_url = self._settings.S3_ENDPOINT
            if not endpoint_url.startswith(('http://', 'https://')):
                protocol = 'https://' if self._settings.S3_SECURE else 'http://'
                endpoint_url = f"{protocol}{endpoint_url}"
            
            self.client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=self._settings.S3_ACCESS_KEY,
                aws_secret_access_key=self._settings.S3_SECRET_KEY,
                use_ssl=self._settings.S3_SECURE,
                config=config
            )
        
        return self.client
    
    async def upload_file(self, bucket: str, key: str, file_path: str, 
                          metadata: Optional[Dict[str, str]] = None) -> bool:
        """Upload file to S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.upload_file(
                    file_path, bucket, key,
                    ExtraArgs={'Metadata': metadata} if metadata else None
                )
            )
            
            logger.debug(f"Uploaded file {file_path} to s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 upload error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {key}: {e}")
            return False
    
    async def upload_fileobj(self, bucket: str, key: str, file_obj: BinaryIO,
                             metadata: Optional[Dict[str, str]] = None) -> bool:
        """Upload file object to S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.upload_fileobj(
                    file_obj, bucket, key,
                    ExtraArgs={'Metadata': metadata} if metadata else None
                )
            )
            
            logger.debug(f"Uploaded file object to s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 upload error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {key}: {e}")
            return False
    
    async def upload_content_sync(self, bucket: str, key: str, content: bytes,
                                  content_type: str = "application/octet-stream",
                                  metadata: Optional[Dict[str, str]] = None) -> bool:
        """Upload content directly to S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                    Metadata=metadata or {}
                )
            )
            
            logger.debug(f"Uploaded content to s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 upload error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {key}: {e}")
            return False
    
    async def download_file(self, bucket: str, key: str, file_path: str) -> bool:
        """Download file from S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.download_file(bucket, key, file_path)
            )
            
            logger.debug(f"Downloaded file s3://{bucket}/{key} to {file_path}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 download error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {key}: {e}")
            return False
    
    async def get_object(self, bucket: str, key: str) -> Optional[bytes]:
        """Get object from S3/MinIO as bytes"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.get_object(Bucket=bucket, Key=key)
            )
            
            logger.debug(f"Retrieved object s3://{bucket}/{key}")
            return response['Body'].read()
            
        except ClientError as e:
            logger.error(f"S3 get object error for {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting {key}: {e}")
            return None
    
    async def delete_object(self, bucket: str, key: str) -> bool:
        """Delete object from S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.delete_object(Bucket=bucket, Key=key)
            )
            
            logger.debug(f"Deleted object s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 delete error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting {key}: {e}")
            return False
    
    async def list_objects(self, bucket: str, prefix: str = "", 
                          max_keys: int = 1000) -> list[Dict[str, Any]]:
        """List objects in S3/MinIO bucket"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
            )
            
            objects = response.get('Contents', [])
            logger.debug(f"Listed {len(objects)} objects in s3://{bucket}/{prefix}")
            return objects
            
        except ClientError as e:
            logger.error(f"S3 list objects error for {prefix}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing {prefix}: {e}")
            return []
    
    async def object_exists(self, bucket: str, key: str) -> bool:
        """Check if object exists in S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.head_object(Bucket=bucket, Key=key)
            )
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"S3 head object error for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking {key}: {e}")
            return False
    
    async def get_object_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata from S3/MinIO"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.head_object(Bucket=bucket, Key=key)
            )
            
            return {
                'size': response.get('ContentLength'),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag'),
                'metadata': response.get('Metadata', {})
            }
            
        except ClientError as e:
            logger.error(f"S3 head object error for {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting metadata for {key}: {e}")
            return None
    
    async def generate_presigned_url(
        self, 
        bucket: str, 
        key: str, 
        options: Optional['PresignOptions'] = None
    ) -> str:
        """Generate presigned URL for object download/upload
        
        If S3_PUBLIC_ENDPOINT is configured, the internal endpoint in the URL
        will be replaced with the public endpoint for browser access.
        """
        try:
            client = self._get_client()
            opts = options or PresignOptions()
            
            params = {
                'Bucket': bucket,
                'Key': key,
            }
            
            # Add response headers if specified
            if opts.response_headers:
                for header_key, header_value in opts.response_headers.items():
                    params[header_key] = header_value
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                None,
                lambda: client.generate_presigned_url(
                    ClientMethod='get_object' if opts.method == 'GET' else 'put_object',
                    Params=params,
                    ExpiresIn=opts.expires_in
                )
            )
            
            # Replace internal endpoint with public endpoint if configured
            public_endpoint = self._settings.S3_PUBLIC_ENDPOINT
            if public_endpoint:
                from urllib.parse import urlparse, urlunparse
                internal_endpoint = self._settings.S3_ENDPOINT
                
                # Parse both URLs
                internal_parsed = urlparse(internal_endpoint)
                public_parsed = urlparse(public_endpoint)
                url_parsed = urlparse(url)
                
                # Replace scheme and netloc with public endpoint
                new_url = url_parsed._replace(
                    scheme=public_parsed.scheme,
                    netloc=public_parsed.netloc
                )
                url = urlunparse(new_url)
                logger.debug(f"Replaced internal endpoint with public: {url}")
            
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {key}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL for {key}: {e}")
            raise

    async def health_check(self) -> bool:
        """Check S3/MinIO connectivity"""
        try:
            client = self._get_client()
            
            # Run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.list_buckets()
            )
            
            return True
            
        except NoCredentialsError:
            logger.error("S3 credentials not configured")
            return False
        except ClientError as e:
            logger.error(f"S3 health check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"S3 health check unexpected error: {e}")
            return False

    async def delete_folder(self, bucket: str, prefix: str) -> bool:
        """Delete all objects with given prefix (folder) from S3/MinIO"""
        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()

            deleted_total = 0
            continuation_token = None

            while True:
                def _list_page():
                    kwargs = {
                        "Bucket": bucket,
                        "Prefix": prefix,
                        "MaxKeys": 1000,
                    }
                    if continuation_token:
                        kwargs["ContinuationToken"] = continuation_token
                    return client.list_objects_v2(**kwargs)

                response = await loop.run_in_executor(None, _list_page)
                objects = response.get("Contents", []) or []

                if objects:
                    keys_to_delete = [{"Key": obj["Key"]} for obj in objects if obj.get("Key")]
                    if keys_to_delete:
                        await loop.run_in_executor(
                            None,
                            lambda: client.delete_objects(
                                Bucket=bucket,
                                Delete={"Objects": keys_to_delete},
                            ),
                        )
                        deleted_total += len(keys_to_delete)

                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")
                if not continuation_token:
                    break

            if deleted_total == 0:
                logger.debug(f"No objects found in s3://{bucket}/{prefix}")
                return True

            logger.info(f"Deleted {deleted_total} objects from s3://{bucket}/{prefix}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 delete folder error for {prefix}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting folder {prefix}: {e}")
            return False


@dataclass
class PresignOptions:
    """Options for presigned URL generation"""
    expires_in: int = 3600  # 1 hour default
    method: str = "GET"
    content_type: Optional[str] = None
    response_headers: Optional[Dict[str, str]] = None


# Global S3 client instance
_s3_client: Optional[S3Client] = None

def get_s3_client() -> S3Client:
    """Get global S3 client instance"""
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
    return _s3_client


# Global S3 manager instance for backward compatibility
s3_manager = get_s3_client()
