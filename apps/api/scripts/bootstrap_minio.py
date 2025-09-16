from app.core.s3 import ensure_bucket
from app.core.config import settings

def main():
    for b in (settings.S3_BUCKET_RAG, settings.S3_BUCKET_ANALYSIS):
        ensure_bucket(b)
        print(f"ensured bucket: {b}")

if __name__ == "__main__":
    main()
