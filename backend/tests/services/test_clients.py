import types
from app.services import clients

def test_qdrant_filter_build(monkeypatch):
    # monkeypatch search to capture arguments
    captured = {}
    class DummyH: 
        def __init__(self): self.score=0.9; self.id="1"; self.payload={"text":"t","document_id":"d","chunk_idx":0,"tags":["a"]}
    def fake_search(collection_name, query_vector, limit, offset, with_payload, query_filter):
        captured['kwargs'] = {'collection_name': collection_name, 'limit': limit, 'offset': offset, 'with_payload': with_payload, 'query_filter': query_filter}
        return [DummyH()]
    monkeypatch.setattr(clients.get_qdrant(), "search", fake_search)
    out = clients.qdrant_search([0.1,0.2], 5, offset=10, doc_id="doc-1", tags=["a","b"])
    assert out and out[0]["payload"]["document_id"] == "d"
    k = captured['kwargs']
    assert k['limit'] == 5 and k['offset'] == 10 and k['with_payload'] is True
    assert k['query_filter'] is not None
