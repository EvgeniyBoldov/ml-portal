"""Run the scope migration against an isolated schema in a disposable PostgreSQL."""
import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('SCOPE_MIGRATION_TEST_URL'), reason='Disposable PostgreSQL is required')
async def test_migration_preserves_links_and_moves_profiles_and_chat_to_slug_scopes():
    engine = create_async_engine(os.environ['SCOPE_MIGRATION_TEST_URL'])
    schema = 'scope_test_' + uuid4().hex
    all_id, project_id, team_id = uuid4(), uuid4(), uuid4()
    doc_id, default_doc_id, user_id, tenant_id, chat_item_id, plan_id = [uuid4() for _ in range(6)]
    statements = [
        "CREATE TYPE memoryscopetype AS ENUM ('team','project')",
        """CREATE TABLE memory_scopes (id uuid PRIMARY KEY, scope_type memoryscopetype NOT NULL,
           key varchar(180) NOT NULL, name text NOT NULL, aliases text[] NOT NULL DEFAULT '{}',
           is_all bool NOT NULL DEFAULT false, project_id uuid, lifecycle_status text DEFAULT 'active',
           deprecated_at timestamptz, CONSTRAINT uq_memory_scopes_type_key UNIQUE(scope_type,key),
           CONSTRAINT ck_memory_scopes_all_key CHECK(key LIKE scope_type::text || '.%'),
           CONSTRAINT ck_memory_scopes_project_type CHECK(project_id IS NULL OR scope_type='project'))""",
        "CREATE UNIQUE INDEX uq_memory_scopes_all_type ON memory_scopes(scope_type) WHERE is_all",
        "CREATE TABLE ragdocuments(id uuid PRIMARY KEY, status text DEFAULT 'indexed')",
        "CREATE TABLE document_memory_scopes(document_id uuid REFERENCES ragdocuments, scope_id uuid REFERENCES memory_scopes, method text, PRIMARY KEY(document_id,scope_id))",
        "CREATE TABLE sources(source_id uuid PRIMARY KEY, meta jsonb)",
        "CREATE TABLE users(id uuid PRIMARY KEY, memory_scope_keys text[])",
        "CREATE TABLE tenants(id uuid PRIMARY KEY, memory_scope_keys text[])",
        "CREATE TABLE chat_memory_items(id uuid PRIMARY KEY, kind text, payload jsonb)",
        "CREATE TABLE models(id uuid PRIMARY KEY, use_for_long_memory bool)",
        "CREATE TABLE long_memory_reindex_requests(id uuid PRIMARY KEY, model_id uuid)",
        """CREATE TABLE system_llm_roles(id uuid PRIMARY KEY, role_type text, is_active bool,
           identity text, mission text, rules text, safety text, output_requirements text, examples jsonb, updated_at timestamptz)""",
        "CREATE TABLE runtime_plans(id uuid PRIMARY KEY, status text, scope_context jsonb, memory_context jsonb)",
        "CREATE TABLE runtime_plan_tasks(id uuid PRIMARY KEY, plan_id uuid, scope_context jsonb)",
        "CREATE TABLE runtime_pauses(id uuid PRIMARY KEY, status text, payload jsonb)",
        "CREATE TABLE chat_turns(id uuid PRIMARY KEY, status text, paused_context jsonb)",
        "CREATE TABLE sandbox_runs(id uuid PRIMARY KEY, paused_context jsonb)",
    ]
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
            await connection.exec_driver_sql(f'SET LOCAL search_path TO {schema},public')
            for statement in statements:
                await connection.exec_driver_sql(statement)
            for id_, key, type_, all_ in [(all_id, 'project.all', 'project', True), (project_id, 'project.dcbox', 'project', False), (team_id, 'team.ops', 'team', False)]:
                await connection.execute(text('INSERT INTO memory_scopes(id,scope_type,key,name,is_all) VALUES(:id,:type,:key,:name,:all)'),
                                         {'id': id_, 'type': type_, 'key': key, 'name': key, 'all': all_})
            for id_ in (doc_id, default_doc_id):
                await connection.execute(text('INSERT INTO ragdocuments(id) VALUES(:id)'), {'id': id_})
            await connection.execute(text("INSERT INTO document_memory_scopes VALUES(:doc,:scope,'explicit')"), {'doc': doc_id, 'scope': project_id})
            await connection.execute(text("INSERT INTO sources VALUES(:doc,'{\"memory\":{\"scope_keys\":[\"project.dcbox\"]}}')"), {'doc': doc_id})
            await connection.execute(text("INSERT INTO users VALUES(:id,ARRAY['team.ops','project.dcbox'])"), {'id': user_id})
            await connection.execute(text("INSERT INTO tenants VALUES(:id,ARRAY['project.all'])"), {'id': tenant_id})
            await connection.execute(text("""INSERT INTO chat_memory_items VALUES(:id,'scope',
                '{"scope_keys":["project.dcbox"],"scope_origins":{"project.dcbox":"chat_focus"}}')"""), {'id': chat_item_id})
            await connection.execute(text("INSERT INTO models VALUES(:id,true)"), {'id': uuid4()})
            await connection.execute(text("""INSERT INTO runtime_plans VALUES(:id,'active',
                '{"keys":["project.dcbox"],"selected":[{"key":"project.dcbox","type":"project"}]}',
                '[{"type":"planner_memory_result","result":{"items":[{"text":"unscoped"}]}}]')"""), {'id': plan_id})
            migration = importlib.import_module('app.migrations.versions.0191_flat_memory_scope_corpora')
            def upgrade(sync_connection):
                original = migration.op
                migration.op = Operations(MigrationContext.configure(sync_connection))
                try:
                    migration.upgrade()
                finally:
                    migration.op = original
            await connection.run_sync(upgrade)
            scopes = dict((await connection.execute(text('SELECT key,id FROM memory_scopes'))).all())
            assert scopes == {'company': all_id, 'dcbox': project_id, 'team-ops': team_id}
            assert (await connection.execute(text('SELECT scope_id FROM document_memory_scopes WHERE document_id=:id'), {'id': doc_id})).scalar_one() == project_id
            assert (await connection.execute(text('SELECT scope_id FROM document_memory_scopes WHERE document_id=:id'), {'id': default_doc_id})).scalar_one() == all_id
            assert (await connection.execute(text('SELECT memory_scope_keys FROM users'))).scalar_one() == ['team-ops', 'dcbox']
            assert (await connection.execute(text('SELECT meta FROM sources'))).scalar_one()['memory']['scope_keys'] == ['dcbox']
            payload = (await connection.execute(text('SELECT payload FROM chat_memory_items'))).scalar_one()
            assert payload['scope_mode'] == 'replace' and payload['scope_keys'] == ['dcbox']
            active = (await connection.execute(text('SELECT scope_context,memory_context FROM runtime_plans'))).one()
            assert active.scope_context['keys'] == ['dcbox'] and active.memory_context == []
            assert (await connection.execute(text('SELECT count(*) FROM long_memory_reindex_requests'))).scalar_one() == 1
    finally:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await engine.dispose()
