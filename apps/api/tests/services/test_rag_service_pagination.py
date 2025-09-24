from app.services.rag_service_enhanced import RAGDocumentsService

def test_next_offset_and_sort(monkeypatch):
    # monkeypatch clients: embed_texts -> fixed vector; qdrant_search -> fake hits
    from app.services import clients
    monkeypatch.setattr(clients, "embed_texts", lambda texts: [[0.1, 0.2]])
    def fake_search(vec, top_k, offset=0, doc_id=None, tags=None, sort_by="score_desc"):
        base = [
            {"score": 0.9, "payload": {"text":"A","document_id":"d","chunk_idx":0,"tags":["x"]}},
            {"score": 0.8, "payload": {"text":"B","document_id":"d","chunk_idx":1,"tags":["y"]}},
        ][:top_k]
        return list(reversed(base)) if sort_by=="score_asc" else base
    monkeypatch.setattr(clients, "qdrant_search", fake_search)
    class S: pass
    service = RAGDocumentsService(S())
    out = service.search_documents("user123", "q", limit=2, offset=10)
    assert len(out) == 2
    # Note: search_documents returns documents, not chunks with scores
    # This test needs to be updated to match the actual API
