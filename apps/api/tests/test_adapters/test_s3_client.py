
import types
import pytest

import app.adapters.s3_client as s3_mod


class DummyError(Exception):
    code = "NoSuchKey"


class DummyMinio:
    def __init__(self, *a, **kw):
        self._buckets = set()
        self._objects = {}

    # Buckets
    def bucket_exists(self, name: str) -> bool:
        return name in self._buckets

    def make_bucket(self, name: str):
        self._buckets.add(name)

    # Objects
    def stat_object(self, bucket: str, key: str):
        if (bucket, key) not in self._objects:
            e = DummyError("no such key")
            raise e
        return types.SimpleNamespace()

    def remove_object(self, bucket: str, key: str):
        self._objects.pop((bucket, key), None)

    # Presigns
    def get_presigned_url(self, method: str, bucket: str, key: str, expires: int, response_headers=None):
        return f"presigned://{method.lower()}/{bucket}/{key}?exp={expires}"


@pytest.fixture(autouse=True)
def patch_minio(monkeypatch):
    monkeypatch.setattr(s3_mod, "Minio", DummyMinio, raising=True)
    # recreate the singleton after patch
    s3_mod.s3_manager = s3_mod.S3Manager()
    yield


def test_ensure_and_presign_put():
    url = s3_mod.s3_manager.generate_presigned_url(
        bucket="x",
        key="a/b/c.txt",
        options=s3_mod.PresignOptions(operation="put", expiry_seconds=600, content_type="text/plain"),
    )
    assert url.startswith("presigned://put/x/a/b/c.txt?exp=600")

def test_exists_and_delete_idempotent():
    mgr = s3_mod.s3_manager
    assert mgr.exists("b", "k") is False
    # After delete still fine
    mgr.delete_object("b", "k")
    assert mgr.exists("b", "k") is False
