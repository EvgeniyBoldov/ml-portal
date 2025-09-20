from .conftest import api

def test_auth_me_unauthorized(client):
    r = client.get(api("/auth/me"))
    assert r.status_code in (401, 403)
    body = r.json()
    assert "error" in body or "ok" in body

def test_auth_me_authorized_header_shape(client):
    # If your app supports test token via env, place it here; otherwise just ensure 401 path is stable
    r = client.get(api("/auth/me"), headers={"Authorization": "Bearer invalid"})
    assert r.status_code in (401, 403)
