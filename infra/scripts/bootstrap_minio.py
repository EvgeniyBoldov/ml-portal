import os
from minio import Minio

# MinIO settings
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
S3_BUCKET_RAG = os.getenv("S3_BUCKET_RAG", "rag")
S3_BUCKET_ANALYSIS = os.getenv("S3_BUCKET_ANALYSIS", "analysis")

def ensure_bucket(bucket_name: str):
    """Create bucket if it doesn't exist"""
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"Created bucket: {bucket_name}")
    else:
        print(f"Bucket already exists: {bucket_name}")

def main():
    for b in (S3_BUCKET_RAG, S3_BUCKET_ANALYSIS):
        ensure_bucket(b)
        print(f"ensured bucket: {b}")

if __name__ == "__main__":
    main()
