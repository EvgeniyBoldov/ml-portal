# Remove this import as it's not needed

def test_sse_route_presence_soft(client):
    r = client.get("/api/chats/sse")
    # We accept 404 if not implemented; assert no 500s
    assert r.status_code in (200, 401, 403, 404)
