
import pytest

from app.core.s3_links import S3LinkFactory, S3ExpiryPolicy, S3ContentType
import app.adapters.s3_client as s3_mod


class DummyMinio:
    def __init__(self, *a, **kw):
        pass

    def bucket_exists(self, name: str) -> bool:
        return True

    def make_bucket(self, name: str):
        return None

    def get_presigned_url(self, method: str, bucket: str, key: str, expires: int, response_headers=None):
        return f"presigned://{method.lower()}/{bucket}/{key}?exp={expires}"


@pytest.fixture(autouse=True)
def patch_minio(monkeypatch):
    monkeypatch.setattr(s3_mod, "Minio", DummyMinio, raising=True)
    # recreate the singleton after patch
    s3_mod.s3_manager = s3_mod.S3Manager()
    yield


def test_document_upload():
    f = S3LinkFactory()
    link = f.for_document_upload(doc_id="123", content_type="application/pdf")
    assert link.bucket == "documents"
    assert link.key == "docs/123"
    assert link.content_type == "application/pdf"
    assert link.expires_in == int(S3ExpiryPolicy.UPLOAD)
    assert link.url.startswith("presigned://put/")

def test_document_download():
    f = S3LinkFactory()
    link = f.for_document_download(doc_id="XYZ")
    assert link.bucket == "documents"
    assert link.key == "docs/XYZ"
    assert link.content_type == S3ContentType.OCTET
    assert link.expires_in == int(S3ExpiryPolicy.DOWNLOAD)
    assert link.url.startswith("presigned://get/")

def test_artifact_put():
    f = S3LinkFactory()
    link = f.for_artifact(job_id="job1", filename="out.json", content_type="application/json")
    assert link.bucket == "artifacts"
    assert link.key == "jobs/job1/out.json"
    assert link.content_type == "application/json"
    assert link.expires_in == int(S3ExpiryPolicy.ARTIFACT)
    assert link.url.startswith("presigned://put/")
