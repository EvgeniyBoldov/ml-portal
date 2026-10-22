"""Regression coverage for the admin scope dependency query on PostgreSQL."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.lifecycle_admin_service import LifecycleAdminService


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("MEMORY_OPERATIONS_TEST_URL"), reason="Disposable PostgreSQL is required")
async def test_scope_dependencies_load_candidate_and_document_ids_without_cast_hydration_error():
    url = os.environ["MEMORY_OPERATIONS_TEST_URL"]
    schema = "memory_scope_deps_" + uuid4().hex
    admin_engine = create_async_engine(url)
    scoped_engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema + ",public"}},
    )
    try:
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        async with scoped_engine.begin() as connection:
            for statement in (
                "CREATE TABLE memory_scopes (id uuid PRIMARY KEY, scope_type text NOT NULL)",
                "CREATE TABLE memory_claim_scopes (claim_id uuid NOT NULL, scope_id uuid NOT NULL)",
                "CREATE TABLE memory_candidate_scopes (candidate_id uuid NOT NULL, scope_id uuid NOT NULL)",
                "CREATE TABLE document_memory_scopes (document_id uuid NOT NULL, scope_id uuid NOT NULL)",
                "CREATE TABLE memory_claims (id uuid PRIMARY KEY, normalized_subject text, memory_item_id uuid)",
                "CREATE TABLE memory_items (id uuid PRIMARY KEY, subject text)",
            ):
                await connection.exec_driver_sql(statement)

        scope_id, candidate_id, document_id = uuid4(), uuid4(), uuid4()
        async with async_sessionmaker(scoped_engine, expire_on_commit=False)() as session:
            await session.execute(text("INSERT INTO memory_scopes VALUES (:id, 'project')"), {"id": scope_id})
            await session.execute(text("INSERT INTO memory_candidate_scopes VALUES (:candidate, :scope)"),
                                  {"candidate": candidate_id, "scope": scope_id})
            await session.execute(text("INSERT INTO document_memory_scopes VALUES (:document, :scope)"),
                                  {"document": document_id, "scope": scope_id})
            await session.commit()

            dependencies = await LifecycleAdminService(session)._memory_scope_dependencies(scope_id)

        by_type = {item["resource_type"]: item for item in dependencies}
        assert by_type["memory_candidates"]["count"] == 1
        assert by_type["memory_candidates"]["entities"][0]["uuid"] == str(candidate_id)
        assert by_type["document_scope_hints"]["count"] == 1
        assert by_type["document_scope_hints"]["will_be"] == "set_null"
        assert by_type["document_scope_hints"]["entities"][0]["uuid"] == str(document_id)
    finally:
        await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await admin_engine.dispose()
