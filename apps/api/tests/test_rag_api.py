from .conftest import api

def test_rag_docs_requires_auth(client):
    r = client.get(api("/rag/docs"))
    assert r.status_code in (401, 403)

def test_rag_register_requires_auth(client):
    r = client.post(api("/rag/docs"), json={"filename": "file.pdf"})
    assert r.status_code in (401, 403)
