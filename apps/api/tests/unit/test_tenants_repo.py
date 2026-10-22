from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.tenants_repo import AsyncTenantsRepository


@pytest.mark.asyncio
async def test_update_preserves_explicit_null_for_nullable_tenant_fields():
    tenant = SimpleNamespace(id=uuid4())
    second_result = SimpleNamespace(scalar_one_or_none=lambda: tenant)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None, second_result]))
    repo = AsyncTenantsRepository(session)

    result = await repo.update(tenant.id, description=None, embedding_model_alias=None)

    update_statement = session.execute.await_args_list[0].args[0]
    compiled = update_statement.compile(dialect=postgresql.dialect())
    assert compiled.params["description"] is None
    assert compiled.params["embedding_model_alias"] is None
    assert result is tenant


@pytest.mark.asyncio
async def test_list_page_applies_search_filters_and_database_pagination():
    page_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ["tenant-row"]))
    count_result = SimpleNamespace(scalar_one=lambda: 201)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[count_result, page_result]))
    repo = AsyncTenantsRepository(session)

    rows, total = await repo.list_page(
        page=2,
        size=100,
        search="operations",
        is_active=True,
        include_deprecated=False,
    )

    count_query, page_query = [call.args[0] for call in session.execute.await_args_list]
    count_sql = str(count_query.compile(dialect=postgresql.dialect()))
    page_compiled = page_query.compile(dialect=postgresql.dialect())
    page_sql = str(page_compiled)
    assert "tenants.name ILIKE" in count_sql
    assert "tenants.description ILIKE" in count_sql
    assert "tenants.is_active IS true" in count_sql
    assert "tenants.lifecycle_status !=" in count_sql
    assert "LIMIT %(param_1)s OFFSET %(param_2)s" in page_sql
    assert page_compiled.params["param_1"] == 100
    assert page_compiled.params["param_2"] == 100
    assert rows == ["tenant-row"]
    assert total == 201
