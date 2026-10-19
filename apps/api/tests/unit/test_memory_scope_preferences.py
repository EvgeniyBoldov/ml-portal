from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.memory_scope_preferences import MemoryScopePreferences
from app.services.memory_scope_preferences_service import MemoryScopePreferencesService, inherit_scope_context


def catalog():
    return [SimpleNamespace(id=uuid4(), key=key, scope_type='project', name=key, is_all=False)
            for key in ['company', 'ops', 'nims', 'dcbox']]


def test_defaults_union_tenant_and_user_without_duplicates():
    context = inherit_scope_context(catalog=catalog(), chat_context={},
                                    tenant_keys=['company', 'ops'], user_keys=['ops', 'nims'])
    assert context.keys == ['company', 'ops', 'nims']
    assert [item.source for item in context.selected] == ['tenant_default', 'user_default', 'user_default']
    assert context.mode == 'inherit'


def test_empty_profiles_use_company_and_explicit_chat_clear_searches_nothing():
    inherited = inherit_scope_context(catalog=catalog(), chat_context={}, user_keys=[], tenant_keys=[])
    assert inherited.keys == ['company']
    cleared = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_mode': 'replace', 'scope_keys': [],
    }}, user_keys=['nims'], tenant_keys=['company'])
    assert cleared.keys == []
    assert cleared.explicit_clear


def test_chat_override_replaces_both_profiles_and_does_not_silently_widen():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_mode': 'replace', 'scope_keys': ['dcbox'], 'scope_origins': {'dcbox': 'chat_focus'},
    }}, user_keys=['nims'], tenant_keys=['company'])
    assert context.keys == ['dcbox']
    assert context.mode == 'replace'


def test_updated_profiles_refresh_inherited_chat_values():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_keys': ['ops'], 'scope_origins': {'ops': 'tenant_default'},
    }}, user_keys=['nims'], tenant_keys=['dcbox'])
    assert context.keys == ['dcbox', 'nims']


def test_deleted_scope_in_explicit_chat_does_not_reintroduce_defaults():
    context = inherit_scope_context(catalog=catalog(), chat_context={'focus': {
        'scope_mode': 'replace', 'scope_keys': ['deleted'],
    }}, user_keys=['nims'], tenant_keys=['company'])
    assert context.keys == []
    assert context.explicit_clear


@pytest.mark.asyncio
async def test_validate_preferences_uses_active_catalog(monkeypatch):
    from app.services import memory_scope_preferences_service as module
    service = MemoryScopePreferencesService(object())
    resolver = AsyncMock(return_value=[catalog()[0]])
    monkeypatch.setattr(module, 'resolve_memory_scopes', resolver)
    assert await service.validate_keys(['company']) == ['company']
    resolver.side_effect = ValueError('Unknown memory scope: removed')
    with pytest.raises(ValueError, match='Unknown'):
        await service.validate_keys(['removed'])
    with pytest.raises(ValidationError):
        MemoryScopePreferences(memory_scope_keys=['x'] * 61)
