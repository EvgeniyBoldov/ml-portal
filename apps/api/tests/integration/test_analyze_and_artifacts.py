import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.analyze import router as analyze_router
from app.api.v1.routers.artifacts import router as artifacts_router

class DummyEmb:
    async def embed_texts(self, texts, *, model="default"):
        # deterministic embeddings (length equals char codes sum % 3 just to vary)
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def embed_query(self, query, *, model="default"):
        return [0.1, 0.2, 0.3]

@pytest.fixture()
def app_with_dummy_emb(monkeypatch):
    from app.api import deps as deps_mod
    monkeypatch.setattr(deps_mod, "get_emb_client", lambda: DummyEmb())
    app = FastAPI()
    app.include_router(analyze_router)
    app.include_router(artifacts_router)
    return app

def test_analyze_stream_sse(app_with_dummy_emb):
    c = TestClient(app_with_dummy_emb)
    r = c.post("/api/v1/analyze/stream", json={"texts": ["a", "b", "c"]}, headers={"Idempotency-Key":"x"})
    assert r.status_code == 200
    t = r.text
    assert "event: meta" in t and "event: token" in t and "event: done" in t

def test_artifact_presign(app_with_dummy_emb, monkeypatch):
    # Patch Minio in s3_client to avoid network
    import app.adapters.s3_client as s3_mod
    class DummyMinio:
        def bucket_exists(self, name): return True
        def make_bucket(self, name): return None
        def get_presigned_url(self, method, bucket, key, expires, response_headers=None):
            return f"presigned://{method.lower()}/{bucket}/{key}?exp={expires}"
    monkeypatch.setattr(s3_mod, "Minio", DummyMinio, raising=True)
    s3_mod.s3_manager = s3_mod.S3Manager()

    c = TestClient(app_with_dummy_emb)
    r = c.post("/api/v1/artifacts/presign", json={"job_id":"j1","filename":"out.json"}, headers={"Idempotency-Key":"y"})
    assert r.status_code == 200
    data = r.json()
    assert data["presigned_url"].startswith("presigned://put/")
    assert data["bucket"] and data["key"]
