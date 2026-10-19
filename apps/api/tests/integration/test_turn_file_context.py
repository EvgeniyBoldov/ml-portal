"""Real PostgreSQL contracts in an isolated schema; no production rows are changed."""
from __future__ import annotations

import importlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import _db_url
from app.models.chat import Chats, ChatMessages
from app.models.chat_attachment import ChatAttachment
from app.models.chat_artifact_reference import ChatArtifactReference
from app.models.chat_turn import ChatTurn
from app.models.chat_context_head import ChatContextHead
from app.models.chat_memory import ChatMemoryItem
from app.models.base import Base
from app.models.runtime_context import ChatArtifactRepresentation
from app.runtime.run_context import RunContext
from app.services.artifact_representation_service import ArtifactRepresentationService
from app.services.file_generation_service import FileGenerationService
from app.services.runtime_run_context_service import RuntimeRunContextService

pytestmark = pytest.mark.skipif(not os.getenv("TURN_FILE_CONTEXT_PG"), reason="Opt in to isolated PostgreSQL tests")


@pytest_asyncio.fixture
async def database(monkeypatch):
    engine = create_async_engine(_db_url())
    schema = "turn_file_" + uuid4().hex
    async with engine.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped = create_async_engine(_db_url(), connect_args={"server_settings": {"search_path": schema}})
    try:
        async with scoped.begin() as connection:
            for name in ("users", "collections", "sandbox_branches"):
                await connection.exec_driver_sql(f"CREATE TABLE {name}(id uuid PRIMARY KEY)")
            await connection.exec_driver_sql("CREATE TYPE chat_role_enum AS ENUM ('system','user','assistant','tool')")
            tables = [model.__table__ for model in (Chats, ChatMessages, ChatTurn, ChatAttachment,
                      ChatArtifactReference, ChatContextHead, ChatMemoryItem)]
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
            await connection.exec_driver_sql("""CREATE TABLE system_llm_roles(role_type text, is_active boolean,
                identity text, mission text, rules text, safety text, output_requirements text,
                updated_at timestamptz, model text)""")
            await connection.exec_driver_sql("INSERT INTO system_llm_roles(role_type,is_active,model) VALUES ('turn_preflight',true,'keep-model')")
            migration = importlib.import_module("app.migrations.versions.0195_turn_file_context")

            def upgrade(sync):
                previous = migration.op
                migration.op = Operations(MigrationContext.configure(sync))
                try:
                    migration.upgrade()
                finally:
                    migration.op = previous

            await connection.run_sync(upgrade)
        objects = {}

        async def upload(bucket, key, file_obj, **kwargs):
            objects[bucket, key] = file_obj.read()
            return True

        async def get(bucket, key):
            return objects.get((bucket, key))

        async def delete(bucket, key):
            objects.pop((bucket, key), None)
            return True

        monkeypatch.setattr("app.adapters.s3_client.s3_manager.upload_fileobj", upload)
        monkeypatch.setattr("app.adapters.s3_client.s3_manager.get_object", get)
        monkeypatch.setattr("app.adapters.s3_client.s3_manager.delete_object", delete)
        monkeypatch.setattr("app.services.chat_attachment_service.ChatAttachmentService._ensure_bucket", AsyncMock())
        yield async_sessionmaker(scoped, expire_on_commit=False)
    finally:
        await scoped.dispose()
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await engine.dispose()


async def seed(sessions):
    owner, chat = uuid4(), uuid4()
    async with sessions() as session:
        await session.execute(text("INSERT INTO users(id) VALUES(:id)"), {"id": owner})
        session.add(Chats(id=chat, owner_id=owner))
        await session.commit()
    return str(owner), str(chat)


@pytest.mark.asyncio
async def test_generated_file_representation_and_run_survive_new_session(database):
    owner, chat = await seed(database)
    run_id = str(uuid4())
    async with database() as session:
        files = FileGenerationService(session)
        artifact = await files.generate(chat_id=chat, owner_id=owner, filename="sample.py", format_name="py",
            content="print('hello')", metadata={"root_run_id": run_id, "deliverable_key": "0"})
        await session.commit()
        same = await files.generate(chat_id=chat, owner_id=owner, filename="sample.py", format_name="py",
            content="print('hello')", metadata={"root_run_id": run_id, "deliverable_key": "0"})
        assert same.artifact_id == artifact.artifact_id
        read = await ArtifactRepresentationService(session).read(artifact_id=artifact.artifact_id,
            chat_id=chat, owner_id=owner, tenant_id=None)
        context = RunContext(original_request="Create example", constraints=["Python"])
        context.add_evidence("file.read", {"artifact_id": artifact.artifact_id}, read)
        await RuntimeRunContextService(session).save(run_id=run_id, chat_id=chat, owner_id=owner, branch_id=None, context=context)
        await session.commit()
    async with database() as session:
        restored = await RuntimeRunContextService(session).load(run_id=run_id, chat_id=chat, owner_id=owner, branch_id=None)
        assert restored.constraints == ["Python"]
        assert restored.evidence[0].data["content"] == "print('hello')"
        cached = await ArtifactRepresentationService(session).read(artifact_id=artifact.artifact_id,
            chat_id=chat, owner_id=owner, tenant_id=None)
        assert cached["reused"] and cached["representation_id"] == read["representation_id"]
        assert await RuntimeRunContextService(session).load(run_id=run_id, chat_id=chat, owner_id=str(uuid4()), branch_id=None) is None
        assert await RuntimeRunContextService(session).load(run_id=run_id, chat_id=chat, owner_id=owner, branch_id="other") is None
        assert (await session.execute(text("SELECT model FROM system_llm_roles"))).scalar_one() == "keep-model"


@pytest.mark.asyncio
async def test_context_and_assistant_are_visible_together_after_commit(database):
    from app.runtime.context_outcome import RuntimeOutcomeProjector
    from app.runtime.turn_state import RuntimeTurnState
    from app.services.chat_context_reducer import ChatContextReducer
    from app.services.chat_context_service import ChatContextService
    from app.runtime.contracts import PipelineRequest
    from app.runtime.pipeline import RuntimePipeline
    from uuid import UUID

    owner, chat = await seed(database)
    run_id, turn_id = uuid4(), uuid4()
    async with database() as session:
        session.add(ChatTurn(id=turn_id, chat_id=UUID(chat), user_id=UUID(owner), runtime_run_id=run_id))
        await session.commit()
        state = RuntimeTurnState(run_id=run_id, chat_id=UUID(chat), user_id=UUID(owner), goal="Create file")
        artifact = await FileGenerationService(session).generate(chat_id=chat, owner_id=owner,
            filename="result.txt", format_name="txt", content="result")
        state.run_context.generated_artifacts = [{"artifact_id": artifact.artifact_id, "file_name": artifact.file_name}]
        state.final_answer = "Created file"
        request = PipelineRequest(request_text="Create file", chat_id=chat, chat_turn_id=str(turn_id),
            user_id=owner, tenant_id=str(uuid4()))
        pipeline = RuntimePipeline(session=session, llm_client=AsyncMock())
        await pipeline._apply_chat_context_outcome(request=request, runtime_state=state,
            branch_id=None, terminal_state="completed", project_context={})
        session.add(ChatMessages(chat_id=UUID(chat), role="assistant", content={"text": "Created file"}))
        # Another request cannot see an uncommitted answer or its context.
        async with database() as reader:
            assert (await reader.execute(select(ChatMessages.id))).first() is None
            assert (await reader.execute(select(ChatMemoryItem.id))).first() is None
        await session.commit()
    async with database() as reader:
        snapshot = await ChatContextService(reader, None, None).load_snapshot(chat_id=chat, owner_id=owner, tenant_id=str(uuid4()))
        assert snapshot.artifacts[0].artifact_id == artifact.artifact_id
        assert snapshot.recent_anchor.assistant_outcome == "Created file"
        assert (await reader.execute(select(ChatMessages.id))).first() is not None


@pytest.mark.asyncio
async def test_history_pages_are_bounded_and_cannot_cross_chat_or_owner(database):
    from uuid import UUID
    from app.services.chat_history_service import ChatHistoryService
    owner, chat = await seed(database)
    _, other_chat = await seed(database)
    async with database() as session:
        session.add_all([ChatMessages(chat_id=UUID(chat), role="user", content={"text": f"message {i}"})
                         for i in range(3)])
        foreign = ChatMessages(chat_id=UUID(other_chat), role="user", content={"text": "foreign"})
        session.add(foreign)
        await session.commit()
        service = ChatHistoryService(session)
        first = await service.read(chat_id=chat, owner_id=owner, before_message_id=None, limit=2)
        second = await service.read(chat_id=chat, owner_id=owner,
            before_message_id=UUID(first["next_before_message_id"]), limit=2)
        assert len(first["messages"]) == 2 and len(second["messages"]) == 1
        assert len({item["message_id"] for item in first["messages"] + second["messages"]}) == 3
        with pytest.raises(ValueError):
            await service.read(chat_id=chat, owner_id=str(uuid4()), before_message_id=None, limit=2)
        with pytest.raises(ValueError):
            await service.read(chat_id=chat, owner_id=owner, before_message_id=foreign.id, limit=2)
