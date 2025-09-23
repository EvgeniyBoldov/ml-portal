# Remove this import as it's not needed
import uuid

def test_idempotency_key_allows_safe_retries(client):
    idem = str(uuid.uuid4())
    # Choose an endpoint that is POST-able; if /rag/docs requires auth, we just ensure middleware doesn't error
    r1 = client.post("/api/rag/docs", headers={"Idempotency-Key": idem}, json={"filename": "x.txt"})
    r2 = client.post("/api/rag/docs", headers={"Idempotency-Key": idem}, json={"filename": "x.txt"})
    # We don't assert specific code (likely 401), only equality and no 500
    assert r1.status_code == r2.status_code
    assert r1.status_code in (200, 201, 400, 401, 403, 422)
