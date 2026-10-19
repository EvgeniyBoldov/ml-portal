"""Exercise migration, generation fencing and durable deletion on disposable PostgreSQL."""
import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import ForeignKeyConstraint, MetaData, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus, Source
from app.services.long_memory_document_service import LongMemoryDocumentService, document_memory_nodes


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('MEMORY_OPERATIONS_TEST_URL'), reason='Disposable PostgreSQL is required')
async def test_document_operations_survive_source_deletion_and_fence_old_progress():
    engine = create_async_engine(os.environ['MEMORY_OPERATIONS_TEST_URL'])
    schema = 'memory_ops_' + uuid4().hex
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
            await connection.exec_driver_sql(f'SET LOCAL search_path TO {schema},public')
            await connection.exec_driver_sql("CREATE TYPE documentstatus AS ENUM ('uploaded','uploading','processing','processed','ready','failed','archived','queued')")
            metadata = MetaData()
            for model in (RAGDocument, RAGStatus, Source):
                table = model.__table__.to_metadata(metadata)
                for constraint in list(table.constraints):
                    if isinstance(constraint, ForeignKeyConstraint):
                        table.constraints.remove(constraint)
                if model is RAGDocument:
                    table._columns.remove(table.c.long_memory_generation)
                await connection.run_sync(lambda sync, table=table: table.create(sync))
            migration = importlib.import_module('app.migrations.versions.0192_long_memory_document_operations')
            def upgrade(sync):
                original = migration.op
                migration.op = Operations(MigrationContext.configure(sync))
                try:
                    migration.upgrade()
                finally:
                    migration.op = original
            await connection.run_sync(upgrade)
        scoped = create_async_engine(os.environ['MEMORY_OPERATIONS_TEST_URL'], connect_args={'server_settings': {'search_path': schema + ',public'}})
        try:
            sessions = async_sessionmaker(scoped, expire_on_commit=False)
            async with sessions() as session:
                doc = RAGDocument(id=uuid4(), tenant_id=uuid4(), user_id=uuid4(), filename='doc.txt', title='Document', s3_key_processed='canonical.json')
                session.add(doc)
                session.add(Source(source_id=doc.id, tenant_id=doc.tenant_id, meta={}))
                await session.commit()
                service = LongMemoryDocumentService(session)
                added = await service.enqueue(doc.id, 'add')
                await session.commit()
                self_same = await service.enqueue(doc.id, 'add')
                assert self_same.id == added.id
                deleted = await service.enqueue(doc.id, 'delete')
                await session.commit()
                assert deleted.generation == added.generation + 1
                await service.project(added, {'steps': {'index': {'status': 'completed', 'metrics': {'facts': 999}}}})
                await session.commit()
                nodes = await document_memory_nodes(session, doc.id)
                assert all(node['status'] == 'queued' and node['metrics']['action'] == 'delete' for node in nodes)
                await session.execute(text('DELETE FROM sources WHERE source_id=:id'), {'id': doc.id})
                await session.execute(text('DELETE FROM ragdocuments WHERE id=:id'), {'id': doc.id})
                await session.commit()
                assert (await service.repository.latest(doc.id)).id == deleted.id
        finally:
            await scoped.dispose()
    finally:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await engine.dispose()
