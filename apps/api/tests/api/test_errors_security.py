# Remove this import as it's not needed

def test_security_headers_present_on_404(client):
    r = client.get("/api/__definitely_missing__")
    # Some stacks return 404 without our middleware; this test is soft
    assert r.status_code == 404
    # Check a couple of common headers if middleware is connected
    hdrs = r.headers
    assert "X-Content-Type-Options" in hdrs
    assert "Referrer-Policy" in hdrs
