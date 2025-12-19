"""
Adapters layer - external integrations.
"""
from .s3_client import S3Client
from .qdrant_client import QdrantClient

__all__ = [
    "S3Client",
    "QdrantClient",
]
