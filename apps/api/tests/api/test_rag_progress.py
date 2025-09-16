from fastapi.testclient import TestClient
from app.main import app

def test_rag_progress_endpoint(monkeypatch):
    from app.services import rag_service
    def fake_progress(session, doc_id):
        return {"id": doc_id, "status": "indexing", "chunks_total": 10, "vectors_total": 8, "updated_at": None}
    monkeypatch.setattr(rag_service, "progress", fake_progress)
    client = TestClient(app)
    r = client.get("/api/rag/123/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "123" and body["status"] == "indexing"
