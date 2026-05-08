from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.ldap_client import LDAPUserProfile
from app.services.ldap_user_service import LDAPUserService


@pytest.fixture
def ldap_settings() -> SimpleNamespace:
    return SimpleNamespace(
        AUTH_LDAP_DEFAULT_TENANT_SLUG="default",
        AUTH_LDAP_UPDATE_PROFILE_ON_LOGIN=True,
        AUTH_LDAP_AUTO_CREATE_USERS=True,
        AUTH_LDAP_DEFAULT_ROLE="reader",
        AUTH_LDAP_ENABLED=True,
        AUTH_LDAP_SERVER_URI="ldap://localhost:389",
        AUTH_LDAP_BIND_DN="cn=svc,dc=example,dc=com",
        AUTH_LDAP_BIND_PASSWORD="secret",
        AUTH_LDAP_USER_SEARCH_BASEDN="dc=example,dc=com",
        AUTH_LDAP_USER_SEARCH_FILTER="(&(objectClass=user)(sAMAccountName={login}))",
        AUTH_LDAP_USER_LOGIN_ATTR="sAMAccountName",
        AUTH_LDAP_USER_EMAIL_ATTR="mail",
        AUTH_LDAP_USER_DISPLAY_NAME_ATTR="displayName",
        AUTH_LDAP_GROUP_MEMBER_ATTR="memberOf",
        AUTH_LDAP_USE_TLS=False,
        AUTH_LDAP_TLS_VERIFY=False,
        AUTH_LDAP_TLS_CA_FILE=None,
        AUTH_LDAP_TIMEOUT_SECONDS=5,
    )


@pytest.fixture
def ldap_service(ldap_settings: SimpleNamespace) -> LDAPUserService:
    session = AsyncMock()
    service = LDAPUserService(session, ldap_settings)  # type: ignore[arg-type]
    service.users_repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_provision_ldap_user_relinks_by_login_and_does_not_create_duplicate(
    ldap_service: LDAPUserService,
) -> None:
    existing_user = SimpleNamespace(
        id=uuid4(),
        auth_provider="ldap",
        is_active=True,
    )
    ldap_service.users_repo.get_by_login_ci.return_value = None
    ldap_service.users_repo.get_by_external_id.return_value = None
    ldap_service.users_repo.get_by_email_ci.return_value = None
    ldap_service.users_repo.get_by_login_ci.side_effect = [None, existing_user]

    profile = LDAPUserProfile(
        login="User.Name",
        email="user.name@example.com",
        full_name="User Name",
        external_id="CN=User Name,OU=Users,DC=example,DC=com",
        groups=["cn=group1,dc=example,dc=com"],
        is_active=True,
    )

    result = await ldap_service._provision_user(profile)

    assert result.success is True
    assert result.is_new is False
    assert result.user == existing_user

    ldap_service.users_repo.update_ldap_identity.assert_awaited_once_with(
        user_id=existing_user.id,
        login=profile.login,
        external_id=profile.external_id,
    )
    ldap_service.users_repo.create.assert_not_called()
    ldap_service.users_repo.update_last_login.assert_awaited_once_with(existing_user.id)
