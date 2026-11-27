import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from uuid import UUID
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routers.durable_runtime import (
    AdmitRunRequest,
    RunResponseRequest,
    ThreadAddress,
    _event_key,
    _event_cursor,
)
from app.api.deps import db_uow, get_bearer_user
from app.api.v1.routers import durable_runtime as durable_api


def _address(**overrides):
    data = {
        "integration_id": "test-adapter",
        "workspace_id": "workspace-1",
        "conversation_id": "conversation-1",
        "thread_id": "thread-1",
        "source_message_id": "message-1",
    }
    data.update(overrides)
    return ThreadAddress(**data)


def test_response_contract_preserves_boolean_false():
    request = RunResponseRequest(event_id="answer-1", pause_id="4bf0c46e-39c7-4a5b-ae6f-6f31b35862d6", value=False)

    assert request.value is False


def test_response_contract_rejects_untyped_integer():
    with pytest.raises(ValidationError):
        RunResponseRequest(event_id="answer-1", pause_id="4bf0c46e-39c7-4a5b-ae6f-6f31b35862d6", value=0)


def test_admission_validates_timezone_and_bounds_context():
    common = {"event_id": "event-1", "text": "Check this", "address": _address()}

    with pytest.raises(ValidationError):
        AdmitRunRequest(**common, timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        AdmitRunRequest(**common, referenced_context={"text": "x" * 9000})


def test_external_event_key_is_scoped_to_workspace():
    from uuid import UUID

    owner = UUID("4bf0c46e-39c7-4a5b-ae6f-6f31b35862d6")
    first = _event_key(owner, "adapter", "event-1", "workspace-a")
    second = _event_key(owner, "adapter", "event-1", "workspace-b")

    assert first != second


def test_sse_reconnect_cursor_uses_last_event_id():
    assert _event_cursor(2, "9") == 9
    assert _event_cursor(12, "9") == 12
    with pytest.raises(HTTPException) as exc:
        _event_cursor(0, "not-a-sequence")
    assert exc.value.status_code == 400


def test_admission_route_is_authenticated_and_feature_gated(monkeypatch):
    app = FastAPI()
    app.include_router(durable_api.router, prefix="/api/v1")
    app.dependency_overrides[get_bearer_user] = lambda: SimpleNamespace(id=UUID(int=1))

    async def fake_uow():
        yield SimpleNamespace()

    app.dependency_overrides[db_uow] = fake_uow
    monkeypatch.setattr(durable_api, "get_settings", lambda: SimpleNamespace(DURABLE_RUNTIME_ENABLED=False))
    response = TestClient(app).post(
        "/api/v1/integrations/durable-runs",
        json={
            "event_id": "event-1",
            "text": "Check this",
            "address": {
                "integration_id": "test-adapter",
                "workspace_id": "workspace-1",
                "conversation_id": "conversation-1",
                "thread_id": "thread-1",
                "source_message_id": "message-1",
            },
        },
    )

    assert response.status_code == 503


