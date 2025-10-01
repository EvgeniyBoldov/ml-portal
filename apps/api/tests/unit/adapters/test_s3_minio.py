import types
import pytest
from app.adapters.impl.s3_minio import MinioStorage

class DummyMinio:
    def __init__(self): self.calls = []
    def put_object(self, b, k, data, length, content_type=None): self.calls.append(("put", b, k, length, content_type))
    def get_object(self, b, k):
        class Resp:
            def read(self): return b"data"
            def close(self): pass
            def release_conn(self): pass
        return Resp()
    def remove_object(self, b, k): self.calls.append(("del", b, k))
    def presigned_get_object(self, b, k, expires): return f"http://s3/{b}/{k}?e={expires}"

@pytest.mark.anyio
async def test_put_get_delete_presign(monkeypatch):
    # Patch internal Minio with our dummy
    import app.adapters.impl.s3_minio as mod
    dummy = DummyMinio()
    monkeypatch.setattr(mod, "Minio", lambda *a, **k: dummy)
    store = MinioStorage(endpoint="x", access_key="y", secret_key="z", secure=False)

    await store.put("b", "k", b"abc", content_type="text/plain")
    data = await store.get("b", "k")
    url = await store.presign_get("b", "k", 77)
    await store.delete("b", "k")

    assert data == b"data"
    assert url.startswith("http://s3/b/k?e=77")
    assert any(c[0] == "put" for c in dummy.calls)
    assert any(c[0] == "del" for c in dummy.calls)
