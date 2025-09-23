from fastapi.testclient import TestClient
from app.main_enhanced import app

def test_rag_search_payload_shape(monkeypatch):
    from app.services import rag_service
    def fake_search(session, query, top_k, offset=0, doc_id=None, tags=None, sort_by="score_desc"):
        return {"results":[{"score":0.5,"text":"hello","doc_id":"d1","chunk_idx":0,"tags":["a"]}], "next_offset": offset+1}
    monkeypatch.setattr(rag_service, "search", fake_search)
    client = TestClient(app)
    r = client.post("/api/rag/search", json={"query":"q","top_k":3,"offset":1,"doc_id":"d1","tags":["a"]})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body and body["results"][0]["doc_id"] == "d1"
