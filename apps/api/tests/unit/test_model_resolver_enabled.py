import time
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.model_resolver import ModelResolver, _cache


@pytest.mark.asyncio
async def test_disabled_alias_cannot_use_cached_shared_provider_name():
    alias = 'llm.disabled-cache-test'
    _cache[alias] = ('shared-provider-model', time.time())
    result = MagicMock()
    result.scalar_one_or_none.return_value = False
    session = AsyncMock()
    session.execute.return_value = result
    with pytest.raises(ValueError, match='disabled'):
        await ModelResolver(session).resolve(alias)
    assert alias not in _cache


@pytest.mark.asyncio
async def test_enabled_alias_can_use_cached_provider_mapping():
    alias = 'llm.enabled-cache-test'
    _cache[alias] = ('provider-model', time.time())
    result = MagicMock()
    result.scalar_one_or_none.return_value = True
    session = AsyncMock()
    session.execute.return_value = result
    try:
        assert await ModelResolver(session).resolve(alias) == 'provider-model'
        session.execute.assert_awaited_once()
    finally:
        ModelResolver.invalidate_cache(alias)
