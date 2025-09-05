from backend.app.core.s3 import ensure_bucket
from backend.app.core.config import settings

def main():
    for b in (settings.S3_BUCKET_RAW, settings.S3_BUCKET_CANONICAL, settings.S3_BUCKET_PREVIEW):
        ensure_bucket(b)
        print(f"ensured bucket: {b}")

if __name__ == "__main__":
    main()
