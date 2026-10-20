"""Run policy migration in an isolated, rolled-back PostgreSQL schema."""
import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("PROMPT_POLICY_MIGRATION_PG"), reason="Explicit PostgreSQL opt-in required")
async def test_known_policy_is_compacted_and_customizations_and_rollback_survive(monkeypatch):
    from app.core.db import _db_url
    migration = importlib.import_module("app.migrations.versions.0197_compact_known_runtime_prompts")
    engine = create_async_engine(_db_url())
    old = {key: "old-" + key for key in migration.FIELDS}
    monkeypatch.setitem(migration.KNOWN_PROFILES, "planner", migration.fingerprint(old))
    schema = "prompt_audit_" + uuid4().hex
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
                await connection.exec_driver_sql(f"SET LOCAL search_path TO {schema}, public")
                await connection.exec_driver_sql("""CREATE TABLE system_llm_roles (
                    id uuid PRIMARY KEY, role_type text, is_active bool, identity text, mission text,
                    rules text, safety text, output_requirements text, extras jsonb, model text,
                    examples jsonb, updated_at timestamptz)""")
                ids = [uuid4(), uuid4()]
                for identity, policy in zip(ids, [old, {**old, "rules": "custom rules"}]):
                    await connection.execute(text("""INSERT INTO system_llm_roles
                        VALUES (:id,'planner',true,:identity,:mission,:rules,:safety,:output_requirements,
                        CAST(:extras AS jsonb),'keep-model',CAST(:examples AS jsonb),now())"""),
                        {**policy, "id": identity, "extras": '{"existing":true}', "examples": '[{"output":"keep-example"}]'})

                def run(sync, action):
                    monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(sync)))
                    getattr(migration, action)()

                await connection.run_sync(run, "upgrade")
                rows = {row["id"]: dict(row) for row in (await connection.execute(text("SELECT * FROM system_llm_roles"))).mappings()}
                assert rows[ids[0]]["rules"] == migration.POLICIES["planner"]["rules"]
                assert rows[ids[0]]["identity"] == old["identity"]
                assert rows[ids[0]]["model"] == "keep-model"
                assert rows[ids[0]]["examples"] == [{"output": "keep-example"}]
                assert rows[ids[0]]["extras"]["existing"]
                assert rows[ids[1]]["rules"] == "custom rules"
                await connection.run_sync(run, "downgrade")
                restored = (await connection.execute(text("SELECT * FROM system_llm_roles WHERE id=:id"), {"id": ids[0]})).mappings().one()
                assert {key: restored[key] for key in migration.FIELDS} == old
                assert restored["extras"] == {"existing": True}
                await connection.run_sync(run, "upgrade")
                await connection.execute(text("UPDATE system_llm_roles SET rules='edited after migration' WHERE id=:id"), {"id": ids[0]})
                await connection.run_sync(run, "downgrade")
                assert (await connection.execute(text("SELECT rules FROM system_llm_roles WHERE id=:id"), {"id": ids[0]})).scalar_one() == "edited after migration"
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('PROMPT_POLICY_MIGRATION_PG'), reason='Explicit PostgreSQL opt-in required')
async def test_planner_branch_policy_migration_preserves_custom_settings(monkeypatch):
    from app.core.db import _db_url
    migration = importlib.import_module('app.migrations.versions.0198_planner_interaction_output_policy')
    engine = create_async_engine(_db_url())
    schema = 'planner_policy_' + uuid4().hex
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
                await connection.exec_driver_sql(f'SET LOCAL search_path TO {schema}, public')
                await connection.exec_driver_sql('CREATE TABLE system_llm_roles (id integer, role_type text, output_requirements text, extras jsonb, updated_at timestamptz)')
                for identity, policy in [(1, migration.OLD), (2, 'custom policy')]:
                    await connection.execute(text("INSERT INTO system_llm_roles VALUES (:id,'planner',:policy,CAST(:extras AS jsonb),now())"), {'id': identity, 'policy': policy, 'extras': '{"keep":true}'})

                def run(sync, action):
                    monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(sync)))
                    getattr(migration, action)()

                await connection.run_sync(run, 'upgrade')
                rows = (await connection.execute(text('SELECT * FROM system_llm_roles ORDER BY id'))).mappings().all()
                assert rows[0]['output_requirements'] == migration.NEW
                assert rows[0]['extras'] == {'keep': True, migration.BACKUP: migration.OLD}
                assert rows[1]['output_requirements'] == 'custom policy'
                await connection.run_sync(run, 'downgrade')
                row = (await connection.execute(text('SELECT * FROM system_llm_roles WHERE id=1'))).mappings().one()
                assert row['output_requirements'] == migration.OLD
                assert row['extras'] == {'keep': True}
                await connection.run_sync(run, 'upgrade')
                await connection.execute(text("UPDATE system_llm_roles SET output_requirements='edited after migration' WHERE id=1"))
                await connection.run_sync(run, 'downgrade')
                assert (await connection.execute(text('SELECT output_requirements FROM system_llm_roles WHERE id=1'))).scalar_one() == 'edited after migration'
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
