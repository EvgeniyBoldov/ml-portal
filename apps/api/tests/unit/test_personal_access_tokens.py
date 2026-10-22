from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services.personal_access_token_service import PersonalAccessTokenService, TOKEN_PATTERN
from app.core.security import create_access_token, create_refresh_token
from app.core.exceptions import UnauthorizedError
from app.services.bearer_authentication_service import BearerAuthenticationService


@pytest.mark.asyncio
async def test_creation_stores_only_digest_and_public_prefix():
    service = PersonalAccessTokenService(object())
    service.repo = SimpleNamespace(create=AsyncMock(side_effect=lambda token: token))
    owner_id = uuid4()
    token, raw = await service.create(user_id=owner_id, name="Integration", expires_days=7)
    assert TOKEN_PATTERN.fullmatch(raw)
    assert token.id.hex in raw
    assert token.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert token.token_prefix == raw[:20]
    assert raw.split(".")[1] not in token.token_prefix
    assert token.user_id == owner_id
    assert datetime.now(timezone.utc) + timedelta(days=6) < token.expires_at


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["valid", "expired", "revoked", "inactive_owner", "wrong_secret"])
async def test_authentication_checks_current_owner_expiration_and_digest(condition):
    token_id = uuid4()
    raw = f"mlp_pat_{token_id.hex}.{secrets.token_urlsafe(32)}"
    token = SimpleNamespace(token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=None)
    user = SimpleNamespace(id=uuid4(), email="test@example.test", role="editor")
    if condition == "expired":
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if condition == "wrong_secret":
        raw = f"mlp_pat_{token_id.hex}.{secrets.token_urlsafe(32)}"
    service = PersonalAccessTokenService(object())
    repo = SimpleNamespace(active_token_owner=AsyncMock(return_value=None if condition in {"revoked", "inactive_owner"} else (token, user)),
        active_tenant_ids=AsyncMock(return_value=[str(uuid4())]), record_use=AsyncMock())
    service.repo = repo
    principal = await service.authenticate(raw)
    if condition == "valid":
        assert principal.id == str(user.id)
        assert principal.role == "reader"
        assert principal.scopes == []
        repo.record_use.assert_awaited_once()
    else:
        assert principal is None
        repo.record_use.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["old_unprefixed_key", "mlp_legacy_key", "mlp_pat_invalid", "mlp_pat_" + "a" * 32 + ".short"])
async def test_legacy_and_malformed_tokens_have_no_fallback(raw):
    service = PersonalAccessTokenService(object())
    service.repo.active_token_owner = AsyncMock()
    assert await service.authenticate(raw) is None
    service.repo.active_token_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_access_jwt_uses_current_user_and_refresh_is_rejected(monkeypatch):
    from app.models.user import Users
    from app.repositories.api_tokens_repo import ApiTokensRepository
    import app.services.bearer_authentication_service as bearer_auth

    user_id = str(uuid4())
    current_user = SimpleNamespace(
        id=UUID(user_id),
        email="current@example.test",
        role="editor",
        is_enabled=True,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, model, identity):
            assert model is Users
            assert identity == current_user.id
            return current_user

    monkeypatch.setattr(bearer_auth, "get_session_factory", lambda: FakeSession)
    monkeypatch.setattr(ApiTokensRepository, "active_tenant_ids", AsyncMock(return_value=["current-tenant"]))
    token = create_access_token(user_id, "stale@example.test", "admin", ["stale-tenant"], ["admin"])
    principal = await BearerAuthenticationService().authenticate(token)
    assert principal.id == user_id
    assert principal.email == "current@example.test"
    assert principal.role == "reader"
    assert principal.tenant_ids == ["current-tenant"]
    assert principal.scopes == []
    with pytest.raises(UnauthorizedError):
        await BearerAuthenticationService().authenticate(create_refresh_token(user_id))


@pytest.mark.asyncio
async def test_personal_token_cannot_be_used_as_access_cookie():
    with pytest.raises(UnauthorizedError):
        await BearerAuthenticationService().authenticate("mlp_pat_invalid", allow_api_token=False)


@pytest.mark.asyncio
async def test_personal_token_authentication_respects_feature_flag(monkeypatch):
    import app.services.bearer_authentication_service as bearer_auth

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: SimpleNamespace(PAT_ENABLED=False))
    with pytest.raises(UnauthorizedError, match="disabled"):
        await BearerAuthenticationService().authenticate(
            "mlp_pat_" + "a" * 32 + "." + "b" * 43
        )


@pytest.mark.asyncio
async def test_personal_token_creation_respects_feature_flag(monkeypatch):
    import app.services.personal_access_token_service as pat_service

    monkeypatch.setattr(pat_service, "get_settings", lambda: SimpleNamespace(PAT_ENABLED=False))
    with pytest.raises(ValueError, match="personal_access_tokens_disabled"):
        await PersonalAccessTokenService(object()).create(
            user_id=uuid4(), name="disabled", expires_days=1
        )


@pytest.mark.asyncio
async def test_revoked_browser_session_rejects_its_access_token(monkeypatch):
    from app.models.user import Users
    from app.services.auth_refresh_session_service import AuthRefreshSessionService
    import app.services.bearer_authentication_service as bearer_auth

    user_id = uuid4()
    current_user = SimpleNamespace(
        id=user_id, email="current@example.test", role="reader", is_enabled=True
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, model, identity):
            assert model is Users
            assert identity == user_id
            return current_user

    monkeypatch.setattr(bearer_auth, "get_session_factory", lambda: FakeSession)
    monkeypatch.setattr(
        AuthRefreshSessionService,
        "family_is_active",
        AsyncMock(return_value=False),
    )
    token = create_access_token(
        str(user_id), "current@example.test", "reader", [], [], family_id=str(uuid4())
    )

    with pytest.raises(UnauthorizedError, match="revoked"):
        await BearerAuthenticationService().authenticate(token)
