from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.user import Users
from app.models.tenant import Tenants
from app.schemas.memory_scope_preferences import MemoryScopePreferences
from app.services.memory_scope_preferences_service import MemoryScopePreferencesService, inherit_scope_context


def catalog():
    return [SimpleNamespace(id=uuid4(), key=key, scope_type=key.split('.')[0], name=key, is_all=key.endswith('.all'))
            for key in ['team.ops', 'team.net', 'team.all', 'project.a', 'project.b', 'project.all']]


def test_empty_preferences_do_not_assign_a_team_or_project():
    context = inherit_scope_context(catalog=catalog(), chat_context={}, user_keys=[], tenant_keys=[])
    assert context.keys == []
    assert not context.explicit_clear
    assert MemoryScopePreferences().memory_scope_keys == []
    for model in (Users, Tenants):
        assert model.__table__.c.memory_scope_keys.server_default.arg == '{}'


def test_chat_branch_overrides_defaults_but_other_branch_is_inherited():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'project_keys': ['b'], 'scope_origins': {'project.b': 'turn'},
    }}, user_keys=['team.net', 'project.a'], tenant_keys=['team.ops'])
    assert context.keys == ['team.net', 'project.b']
    assert [item.source for item in context.selected] == ['user_default', 'chat_focus']


def test_runtime_projection_retains_tenant_origin_and_common_project_selector():
    from app.runtime.pipeline import _project_context_payload
    context = inherit_scope_context(catalog=catalog(), chat_context={}, user_keys=[], tenant_keys=['team.ops'])
    payload = _project_context_payload(context, {})
    assert payload['scope_source'] == 'tenant_default'
    assert payload['scope_origins'] == {'team.ops': 'tenant_default'}
    assert payload['execution_context']['project_keys'] == ['project.all']
    assert payload['scope_context']['keys'] == ['team.ops']


def test_updated_profiles_replace_inherited_values_without_changing_explicit_focus():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_keys': ['team.ops', 'project.a'], 'project_keys': ['a'], 'team_keys': ['ops'],
        'scope_origins': {'team.ops': 'tenant_default', 'project.a': 'user_default'},
    }}, user_keys=['project.b'], tenant_keys=['team.net'])
    assert context.keys == ['team.net', 'project.b']


def test_clear_and_stale_scopes_do_not_reintroduce_defaults():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_keys': ['project.deleted'], 'suppress_team_default': True, 'suppress_project_default': True,
    }}, user_keys=['project.a'], tenant_keys=['team.ops'])
    assert context.keys == []
    assert context.explicit_clear


@pytest.mark.asyncio
async def test_preferences_reject_all_unknown_and_deprecated_keys(monkeypatch):
    from app.services import memory_scope_preferences_service as module
    service = MemoryScopePreferencesService(object())
    resolver = AsyncMock(return_value=[catalog()[-1]])
    monkeypatch.setattr(module, 'resolve_memory_scopes', resolver)
    with pytest.raises(ValueError, match='concrete'):
        await service.validate_keys(['project.all'])
    resolver.side_effect = ValueError('Unknown memory scope: project.deleted')
    with pytest.raises(ValueError, match='Unknown'):
        await service.validate_keys(['project.deleted'])
    with pytest.raises(ValidationError):
        await service.validate_keys(None)


@pytest.mark.asyncio
async def test_preferences_fit_persisted_chat_branch_limits(monkeypatch):
    from app.services import memory_scope_preferences_service as module
    rows = [SimpleNamespace(key=f'team.{index}', scope_type='team', is_all=False) for index in range(31)]
    monkeypatch.setattr(module, 'resolve_memory_scopes', AsyncMock(return_value=rows))
    with pytest.raises(ValidationError):
        await MemoryScopePreferencesService(object()).validate_keys([row.key for row in rows])


@pytest.mark.asyncio
async def test_update_user_validates_and_flushes_without_committing(monkeypatch):
    from app.services import memory_scope_preferences_service as module
    user_id = uuid4()
    user = SimpleNamespace(lifecycle_status='active', memory_scope_keys=[])
    session = SimpleNamespace(get=AsyncMock(return_value=user), flush=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(module, 'resolve_memory_scopes', AsyncMock(return_value=[catalog()[0]]))
    service = MemoryScopePreferencesService(session)
    assert await service.update_user(user_id, [' Team.Ops ', 'team.ops']) == ['team.ops']
    assert user.memory_scope_keys == ['team.ops']
    session.get.assert_awaited_once_with(Users, user_id)
    session.flush.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_reads_preferences_for_current_principal_and_tenant(monkeypatch):
    from app.services import memory_scope_preferences_service as module
    user_id, tenant_id = uuid4(), uuid4()
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(lifecycle_status='active', memory_scope_keys=['team.net'])))
    monkeypatch.setattr(module, 'list_memory_scopes', AsyncMock(return_value=catalog()))
    service = MemoryScopePreferencesService(session)
    service.tenants.get_by_id = AsyncMock(return_value=SimpleNamespace(lifecycle_status='active', memory_scope_keys=['team.ops', 'project.a']))
    context = await service.resolve_context(
        user_id=user_id, tenant_id=tenant_id, chat_context={},
    )
    assert context.keys == ['team.net', 'project.a']
    assert session.get.await_args_list[0].args == (Users, user_id)
    service.tenants.get_by_id.assert_awaited_once_with(tenant_id)
