import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.routers.chat import router as chat_router

class DummyLLM:
    async def chat(self, messages, **params): return {"ok": True, "echo": messages}
    async def chat_stream(self, messages, **params):
        for t in ["one", "two", "three"]:
            yield t

@pytest.fixture()
def app_with_dummy_llm(monkeypatch):
    from app.api import deps as deps_mod
    monkeypatch.setattr(deps_mod, "get_llm_client", lambda: DummyLLM())

    app = FastAPI()
    app.include_router(chat_router)
    return app

def test_chat_stream_sse(app_with_dummy_llm):
    client = TestClient(app_with_dummy_llm)
    resp = client.post("/api/v1/chat/stream", json={"messages":[{"role":"user","content":"hi"}]})
    assert resp.status_code == 200
    # SSE frames are separated by double newline; ensure tokens present
    text = resp.text
    assert "event: token" in text
    assert "data: one" in text and "data: three" in text
    assert "event: done" in text
