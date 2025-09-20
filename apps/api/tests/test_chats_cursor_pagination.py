from .conftest import api

def test_messages_cursor_requires_auth(client):
    r = client.get(api("/chats/00000000-0000-0000-0000-000000000000/messages"))
    assert r.status_code in (401, 403)
