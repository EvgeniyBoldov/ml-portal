from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

from app.api.v1.routers.security import LoginRequest, login


@pytest.mark.asyncio
async def test_login_commits_when_ldap_user_provisioned():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: []))
    session.commit = AsyncMock()

    payload = LoginRequest(login="ldap-user", password="secret")
    response = Response()

    settings = SimpleNamespace(
        AUTH_LDAP_ENABLED=True,
        JWT_ACCESS_TTL_MINUTES=15,
        JWT_REFRESH_TTL_DAYS=30,
    )

    user = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        email="ldap@example.com",
        role="reader",
        login="ldap-user",
    )

    local_service = MagicMock()
    local_service.authenticate_user = AsyncMock(return_value=None)

    ldap_service = MagicMock()
    ldap_service.authenticate_and_provision = AsyncMock(
        return_value=SimpleNamespace(success=True, user=user, is_new=True, error=None)
    )

    with (
        patch("app.api.v1.routers.security.get_settings", return_value=settings),
        patch("app.api.v1.routers.security.AsyncUsersService", return_value=local_service),
        patch("app.api.v1.routers.security.LDAPUserService", return_value=ldap_service),
        patch("app.api.v1.routers.security.create_access_token", return_value="access"),
        patch("app.api.v1.routers.security.create_refresh_token", return_value="refresh"),
    ):
        result = await login(payload=payload, response=response, session=session, _rl=None)

    session.commit.assert_awaited_once()
    assert result.user.email == "ldap@example.com"
    assert result.access_token == "access"
    assert result.refresh_token == "refresh"
