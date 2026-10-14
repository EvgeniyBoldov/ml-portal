from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

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
        assert principal.role == "editor"
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
async def test_access_jwt_remains_valid_and_refresh_is_rejected():
    user_id = str(uuid4())
    token = create_access_token(user_id, "user@example.test", "reader", [], [])
    assert (await BearerAuthenticationService().authenticate(token)).id == user_id
    with pytest.raises(UnauthorizedError):
        await BearerAuthenticationService().authenticate(create_refresh_token(user_id))


@pytest.mark.asyncio
async def test_personal_token_cannot_be_used_as_access_cookie():
    with pytest.raises(UnauthorizedError):
        await BearerAuthenticationService().authenticate("mlp_pat_invalid", allow_api_token=False)
