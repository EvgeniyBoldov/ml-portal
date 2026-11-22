from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import RbacRuleDuplicateError, ValidationError
from app.services.rbac_service import RbacService


@pytest.fixture
def service(monkeypatch):
    session = AsyncMock()
    scalar_result = Mock()
    scalar_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=scalar_result)
    service = RbacService(session)
    rule = SimpleNamespace(
        id=uuid4(),
        level="tenant",
        owner_user_id=None,
        owner_tenant_id=uuid4(),
        owner_platform=False,
        resource_type="agent",
        resource_id=uuid4(),
        effect="allow",
        lifecycle_status="active",
    )
    service.get_rule = AsyncMock(return_value=rule)
    service._validate_resource_binding = AsyncMock()
    service.rule_repo.update = AsyncMock(side_effect=lambda value: value)
    return service, session, rule


@pytest.mark.asyncio
async def test_update_rule_changes_level_and_owner_binding(service):
    rbac, _, rule = service
    user_id = uuid4()

    result = await rbac.update_rule(
        rule.id,
        level="user",
        owner_user_id=user_id,
        owner_tenant_id=None,
        owner_platform=False,
    )

    assert result.level == "user"
    assert result.owner_user_id == user_id
    assert result.owner_tenant_id is None
    assert result.owner_platform is False


@pytest.mark.asyncio
async def test_update_rule_platform_level_clears_scoped_owners(service):
    rbac, _, rule = service

    result = await rbac.update_rule(rule.id, level="platform", owner_platform=True)

    assert result.level == "platform"
    assert result.owner_user_id is None
    assert result.owner_tenant_id is None
    assert result.owner_platform is True


@pytest.mark.asyncio
async def test_update_rule_requires_owner_for_non_platform_level(service):
    rbac, _, rule = service

    with pytest.raises(ValidationError, match="tenant_owner_required"):
        await rbac.update_rule(rule.id, level="tenant")


@pytest.mark.asyncio
async def test_update_rule_rejects_duplicate_owner_resource_binding(service):
    rbac, session, rule = service
    session.execute.return_value.scalar_one_or_none.return_value = uuid4()

    with pytest.raises(RbacRuleDuplicateError):
        await rbac.update_rule(
            rule.id,
            level="user",
            owner_user_id=uuid4(),
            owner_platform=False,
        )

    rbac.rule_repo.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "owner_user_id", "owner_tenant_id", "owner_platform", "message"),
    [
        ("platform", uuid4(), None, False, "invalid_owner_for_platform_level"),
        ("platform", None, None, False, "invalid_owner_for_platform_level"),
        ("tenant", uuid4(), uuid4(), False, "tenant_owner_required"),
        ("user", None, uuid4(), False, "user_owner_required"),
        ("mystery", None, None, True, "invalid_level"),
    ],
)
async def test_create_rule_rejects_owner_that_does_not_match_level(
    service, level, owner_user_id, owner_tenant_id, owner_platform, message,
):
    rbac, _, _ = service
    rbac.rule_repo.create = AsyncMock()

    with pytest.raises(ValidationError, match=message):
        await rbac.create_rule(
            level=level,
            resource_type="agent",
            resource_id=uuid4(),
            effect="allow",
            owner_user_id=owner_user_id,
            owner_tenant_id=owner_tenant_id,
            owner_platform=owner_platform,
        )

    rbac.rule_repo.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "owner_user_id", "owner_tenant_id", "owner_platform"),
    [
        ("platform", None, None, True),
        ("tenant", None, uuid4(), False),
        ("user", uuid4(), None, False),
    ],
)
async def test_create_rule_accepts_owner_binding_for_each_level(
    service, level, owner_user_id, owner_tenant_id, owner_platform,
):
    rbac, _, _ = service
    rbac.rule_repo.create = AsyncMock(side_effect=lambda rule: rule)

    result = await rbac.create_rule(
        level=level,
        resource_type="agent",
        resource_id=uuid4(),
        effect="allow",
        owner_user_id=owner_user_id,
        owner_tenant_id=owner_tenant_id,
        owner_platform=owner_platform,
    )

    assert result.level == level
    assert result.owner_user_id == owner_user_id
    assert result.owner_tenant_id == owner_tenant_id
    assert result.owner_platform is owner_platform
    rbac.rule_repo.create.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_explain_access_uses_user_group_and_matches_check_access(service, monkeypatch):
    from app.schemas.rbac import ExplainAccessRequest
    from app.services import rbac_service

    rbac, session, rule = service
    user_id, tenant_id = uuid4(), uuid4()
    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=user_id, login="admin")),
        get_default_tenant=AsyncMock(return_value=tenant_id),
    )
    monkeypatch.setattr(rbac_service, "AsyncUsersRepository", Mock(return_value=users))
    session.get.return_value = SimpleNamespace(name="Admins")
    rbac.rule_repo._find_user_rule = AsyncMock(return_value=rule)
    rbac.rule_repo._find_tenant_rule = AsyncMock(return_value=None)
    platform = SimpleNamespace(id=uuid4(), effect="deny")
    rbac.rule_repo._find_platform_rule = AsyncMock(return_value=platform)

    request = ExplainAccessRequest(user_id=user_id, resource_type="agent", resource_id=rule.resource_id)
    result = await rbac.explain_access(request)

    assert result.effect == await rbac.check_access(user_id, tenant_id, "agent", rule.resource_id)
    assert [(layer.level, layer.owner_name, layer.rule_id, layer.effect) for layer in result.layers] == [
        ("user", "admin", rule.id, "allow"),
        ("tenant", "Admins", None, None),
        ("platform", None, platform.id, "deny"),
        ("default", None, None, "deny"),
    ]
    rbac.rule_repo._find_tenant_rule.assert_awaited_once_with(tenant_id, "agent", rule.resource_id)


@pytest.mark.asyncio
async def test_explain_access_platform_without_rule_returns_default_deny(service):
    from app.schemas.rbac import ExplainAccessRequest

    rbac, session, rule = service
    request = ExplainAccessRequest(resource_type="agent", resource_id=rule.resource_id)

    result = await rbac.explain_access(request)

    assert result.effect == "deny"
    assert [(layer.level, layer.effect) for layer in result.layers] == [
        ("platform", None),
        ("default", "deny"),
    ]
    session.execute.assert_awaited_once()
