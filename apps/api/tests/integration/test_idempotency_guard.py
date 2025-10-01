import types
import asyncio
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.api.deps_idempotency import idempotency_guard

class DummyRedis:
    def __init__(self): self.store = {}
    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    import app.api.deps_idempotency as mod
    monkeypatch.setattr(mod, "get_redis", lambda: DummyRedis())

def test_idempotency_guard_conflict():
    app = FastAPI()

    @app.post("/x", dependencies=[Depends(lambda request: idempotency_guard(request, scope="test"))])
    def post_x():
        return {"ok": True}

    client = TestClient(app)
    hdrs = {"Idempotency-Key": "same-key"}
    r1 = client.post("/x", headers=hdrs)
    r2 = client.post("/x", headers=hdrs)
    assert r1.status_code == 200
    assert r2.status_code == 409
    assert r2.headers.get("Retry-After") is not None

def test_idempotency_guard_absent_header_allows():
    app = FastAPI()
    @app.post("/y", dependencies=[Depends(lambda request: idempotency_guard(request, scope="test"))])
    def post_y():
        return {"ok": True}
    client = TestClient(app)
    r = client.post("/y")  # no header
    assert r.status_code == 200
