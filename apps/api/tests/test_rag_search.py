from .conftest import api

def test_rag_search_endpoint_exists(client):
    r = client.post(api("/rag/search"), json={"query": "hello"})
    # Depending on wiring, unauth or 200 with empty results; we just assert it's not 404
    assert r.status_code != 404
