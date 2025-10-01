
import io
import pytest
from app.adapters.impl.s3_minio import MinioStorage

class DummyMinio:
    def __init__(self, *a, **k): self.objects = {}
    def bucket_exists(self, b): return True
    def make_bucket(self, b): pass
    def put_object(self, bucket, key, body, size, content_type=None):
        self.objects[(bucket,key)] = body.read()
    def get_object(self, bucket, key):
        class Obj:
            def __init__(self, data): self._d = data
            def read(self): return self._d
            def close(self): pass
            def release_conn(self): pass
        return Obj(self.objects[(bucket,key)])
    def remove_object(self, bucket, key):
        self.objects.pop((bucket,key), None)
    def get_presigned_url(self, *_a, **_k): return "http://example/presigned"

@pytest.fixture(autouse=True)
def patch_minio(monkeypatch):
    monkeypatch.setattr("app.adapters.impl.s3_minio.Minio", DummyMinio)

def test_put_get_delete():
    s3 = MinioStorage(endpoint="minio:9000", access_key="x", secret_key="y")
    s3.put("b","k", io.BytesIO(b"hello"), content_type="text/plain")
    assert s3.get("b","k") == b"hello"
    url = s3.presign_get("b","k")
    assert url.startswith("http")
    s3.delete("b","k")
