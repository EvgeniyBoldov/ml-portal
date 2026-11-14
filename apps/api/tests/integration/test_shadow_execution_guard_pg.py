"""Shadow admission fences retries using isolated temporary PostgreSQL tables."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.shadow_invocation import ShadowInvocation
from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError
from app.services.shadow_execution_guard_service import ShadowExecutionGuardService

pytestmark = pytest.mark.skipif(os.getenv("SHADOW_WORKFLOW_PG") != "1", reason="requires PostgreSQL")


@pytest.mark.asyncio
@pytest.mark.parametrize("leased", [False, True])
async def test_shadow_guard_blocks_duplicates_and_stale_claims(leased):
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text('''CREATE TEMP TABLE shadow_execution_guards (
                    id uuid primary key, claim_id uuid not null, active boolean not null,
                    calls jsonb not null, created_at timestamptz default now(), updated_at timestamptz default now()
                ) ON COMMIT DROP'''))
                await connection.execute(text('''CREATE TEMP TABLE shadow_invocations (
                    id uuid primary key, user_id uuid not null, tenant_id uuid not null,
                    agent varchar(255) not null, data jsonb not null, scopes jsonb not null,
                    request_id varchar(255) not null, idempotency_key varchar(255), scope_keys jsonb,
                    request_fingerprint varchar(64), status varchar(20) not null, result jsonb,
                    error varchar(255), claim_id uuid, delivered_at timestamptz,
                    created_at timestamptz default now(), updated_at timestamptz default now()
                ) ON COMMIT DROP'''))
                factory = async_sessionmaker(connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
                invocation_id, claim_id = uuid4(), uuid4()
                if leased:
                    async with factory() as session:
                        session.add(ShadowInvocation(id=invocation_id, user_id=uuid4(), tenant_id=uuid4(),
                            agent="shadow", data={}, scopes=[], request_id="guard-test", status="running", claim_id=claim_id))
                        await session.commit()
                guard = ShadowExecutionGuardService(factory, run_id=uuid4(), claim_id=claim_id,
                                                    invocation_id=invocation_id if leased else None)
                await guard.start()
                call = dict(operation="test.write", target="target", arguments={"value": 1})
                key = await guard.admit(**call)
                with pytest.raises(RuntimeExecutionGuardError) as caught:
                    await guard.admit(**call)
                assert caught.value.code == "tool_outcome_unknown"
                await guard.complete(key, success=True)
                with pytest.raises(RuntimeExecutionGuardError) as caught:
                    await guard.admit(**call)
                assert caught.value.code == "duplicate_execution_blocked"
                if leased:
                    next_claim = uuid4()
                    async with factory() as session:
                        row = await session.get(ShadowInvocation, invocation_id)
                        row.claim_id = next_claim
                        await session.commit()
                    # Claim revocation applies before a replacement ledger is started.
                    with pytest.raises(RuntimeExecutionGuardError) as caught:
                        await guard.admit(operation="test.write", target="target", arguments={"value": 2})
                    assert caught.value.code == "execution_guard_stale"
                    replacement = ShadowExecutionGuardService(factory, run_id=uuid4(), claim_id=next_claim,
                                                             invocation_id=invocation_id)
                    await replacement.start()
                    await guard.finish()
                    with pytest.raises(RuntimeExecutionGuardError) as caught:
                        await replacement.admit(**call)
                    assert caught.value.code == "duplicate_execution_blocked"
                    key2 = await replacement.admit(operation="test.write", target="target", arguments={"value": 2})
                    await replacement.complete(key2, success=None)
                    await replacement.finish()
                await guard.finish()
                with pytest.raises(RuntimeExecutionGuardError):
                    await guard.admit(operation="test.write", target="target", arguments={"value": 3})
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shadow_migration_upgrade_and_downgrade():
    from importlib import import_module
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    migration = import_module("app.migrations.versions.0213_shadow_runtime_tools")
    engine = create_async_engine(get_settings().ASYNC_DB_URL)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            original_op = migration.op
            try:
                schema = "shadow_migration_" + uuid4().hex
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.execute(text('CREATE TABLE shadow_invocations (id uuid primary key)'))
                def check(sync_connection):
                    migration.op = Operations(MigrationContext.configure(sync_connection))
                    migration.upgrade()
                    assert "scope_keys" in {column["name"] for column in inspect(sync_connection).get_columns("shadow_invocations", schema=schema)}
                    assert inspect(sync_connection).has_table("shadow_execution_guards", schema=schema)
                    migration.downgrade()
                    assert not inspect(sync_connection).has_table("shadow_execution_guards", schema=schema)
                    assert "scope_keys" not in {column["name"] for column in inspect(sync_connection).get_columns("shadow_invocations", schema=schema)}
                await connection.run_sync(check)
            finally:
                migration.op = original_op
                await transaction.rollback()
    finally:
        await engine.dispose()
