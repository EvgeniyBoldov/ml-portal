from app.runtime.redactor import RuntimeRedactor


def test_runtime_redactor_redacts_nested_secrets_and_dsn_password():
    redactor = RuntimeRedactor()
    payload = {
        "db_dsn": "postgresql://user:secret@localhost:5432/app",
        "nested": {
            "token": "abc123",
            "authorization": "Bearer top-secret-token",
            "items": [{"api_key": "key-1"}],
        },
        "text": "password=hunter2 token=abc123",
    }

    redacted = redactor.redact(payload)

    assert redacted["db_dsn"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["nested"]["authorization"] == "***"
    assert redacted["nested"]["items"][0]["api_key"] == "***"
    assert "hunter2" not in redacted["text"]
    assert "abc123" not in redacted["text"]
