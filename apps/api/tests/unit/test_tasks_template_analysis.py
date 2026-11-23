"""Unit tests for app/workers/tasks_template_analysis.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.services.collection.template_contract import (
    ScalarField,
    TableColumn,
    TableField,
    TemplateContract,
)
from app.workers import tasks_template_analysis

COLLECTION_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ROW_UUID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_contract() -> TemplateContract:
    return TemplateContract(
        fields=[
            ScalarField(key="title_field", label="Title"),
            ScalarField(key="date_field", label="Date"),
            TableField(key="items", label="Items", columns=[TableColumn(key="name", label="Name")]),
        ]
    )


def make_layout(**overrides) -> SimpleNamespace:
    layout = SimpleNamespace(
        format="xlsx",
        title="Invoice",
        version="v2",
        sheets=["S1", "S2"],
        tokens=["t1", "t2", "t3"],
        scalar_keys=["a", "b"],
        table_prefixes=["p"],
        table_regions=["r1", "r2"],
        fence_blocks=["f"],
    )
    for key, value in overrides.items():
        setattr(layout, key, value)
    return layout


def make_node(key: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(node_key=key, status=status)


def install_retry(monkeypatch, task) -> list:
    attempts: list = []

    def retry(exc=None, **_kwargs):
        attempts.append(exc)
        raise exc

    monkeypatch.setattr(task, "retry", retry)
    return attempts


def install_run_context(monkeypatch, *, collection, get_row_results, update_results=None, nodes=()) -> SimpleNamespace:
    session = SimpleNamespace(commit=AsyncMock())
    instances: list = []
    get_by_id = AsyncMock(return_value=collection)
    ensure_contract_fields_present = AsyncMock()
    get_row_by_id = AsyncMock(side_effect=list(get_row_results))
    update_row = AsyncMock(side_effect=list(update_results) if update_results is not None else None)
    status_repo = SimpleNamespace(
        upsert_node=AsyncMock(),
        get_nodes_by_row_id=AsyncMock(return_value=list(nodes)),
    )

    class FakeCollectionService:
        def __init__(self, session_arg) -> None:
            self.get_by_id = get_by_id
            self.ensure_contract_fields_present = ensure_contract_fields_present
            self.get_row_by_id = get_row_by_id
            self.update_row = update_row
            instances.append(self)

    @asynccontextmanager
    async def scope():
        yield session

    monkeypatch.setattr(tasks_template_analysis, "get_worker_session", scope)
    monkeypatch.setattr("app.services.collection_service.CollectionService", FakeCollectionService)
    monkeypatch.setattr(tasks_template_analysis, "AsyncTemplateAnalysisStatusRepository", lambda _s: status_repo)

    return SimpleNamespace(
        session=session,
        instances=instances,
        get_by_id=get_by_id,
        ensure=ensure_contract_fields_present,
        get_row_by_id=get_row_by_id,
        update_row=update_row,
        status_repo=status_repo,
        collection=collection,
    )


def install_s3(monkeypatch, payload) -> SimpleNamespace:
    manager = SimpleNamespace(get_object=AsyncMock(return_value=payload))
    monkeypatch.setattr("app.adapters.s3_client.s3_manager", manager)
    return manager


def install_layout_parser(monkeypatch, layout) -> list:
    instances: list = []

    class FakeLayoutParser:
        def __init__(self) -> None:
            self.parse = Mock(return_value=layout)
            instances.append(self)

    monkeypatch.setattr(tasks_template_analysis, "TemplateLayoutParser", FakeLayoutParser)
    return instances


def install_schema_builder(monkeypatch, contract) -> list:
    instances: list = []

    class FakeSchemaBuilder:
        def __init__(self, *, llm) -> None:
            self.llm = llm
            self.build = AsyncMock(return_value=contract)
            instances.append(self)

    monkeypatch.setattr(tasks_template_analysis, "TemplateSchemaBuilder", FakeSchemaBuilder)
    return instances


def install_description_builder(monkeypatch, description) -> list:
    instances: list = []

    class FakeDescriptionBuilder:
        def __init__(self, *, llm) -> None:
            self.llm = llm
            self.build = AsyncMock(return_value=description)
            instances.append(self)

    monkeypatch.setattr(tasks_template_analysis, "TemplateDescriptionBuilder", FakeDescriptionBuilder)
    return instances


def install_orchestrator(monkeypatch, task_id: str) -> SimpleNamespace:
    orchestrator = SimpleNamespace(enqueue_description=Mock(return_value=task_id))
    monkeypatch.setattr(tasks_template_analysis, "TemplateAnalysisOrchestrator", orchestrator)
    return orchestrator


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_serialize_analysis_nodes_converts_datetimes():
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    finished = datetime(2026, 1, 2, 3, 4, 6, tzinfo=timezone.utc)
    nodes = [
        SimpleNamespace(
            node_key="schema",
            status="completed",
            error_short=None,
            metrics_json={"a": 1},
            started_at=started,
            finished_at=finished,
        )
    ]

    assert tasks_template_analysis._serialize_analysis_nodes(nodes) == [
        {
            "node_key": "schema",
            "status": "completed",
            "error_short": None,
            "metrics_json": {"a": 1},
            "started_at": "2026-01-02T03:04:05+00:00",
            "finished_at": "2026-01-02T03:04:06+00:00",
        }
    ]


def test_serialize_analysis_nodes_defaults_missing_datetimes_to_none():
    nodes = [SimpleNamespace(node_key="description", status="failed", error_short="boom", metrics_json=None)]

    serialized = tasks_template_analysis._serialize_analysis_nodes(nodes)

    assert serialized[0]["started_at"] is None
    assert serialized[0]["finished_at"] is None


def test_build_schema_metrics_returns_exact_dict():
    metrics = tasks_template_analysis._build_schema_metrics(
        row={"title": "Row title", "template_version": "9"},
        filename="invoice.xlsx",
        layout=make_layout(),
        contract=make_contract(),
    )

    assert metrics == {
        "filename": "invoice.xlsx",
        "title": "Invoice",
        "version": "v2",
        "format": "xlsx",
        "sheet_count": 2,
        "sheet_names": ["S1", "S2"],
        "token_count": 3,
        "scalar_key_count": 2,
        "table_prefix_count": 1,
        "table_region_count": 2,
        "fence_block_count": 1,
        "field_count": 3,
        "scalar_field_count": 2,
        "table_field_count": 1,
        "schema_summary": "3 fields, 1 tables",
        "schema_preview": ["title_field", "date_field", "items"],
    }


def test_build_schema_metrics_falls_back_to_row_then_filename():
    row_values = {"title": "Row title", "template_version": "v1"}

    metrics = tasks_template_analysis._build_schema_metrics(
        row=row_values,
        filename="fallback.xlsx",
        layout=make_layout(title="", version=None),
        contract=make_contract(),
    )
    assert metrics["title"] == "Row title"
    assert metrics["version"] == "v1"

    metrics = tasks_template_analysis._build_schema_metrics(
        row={},
        filename="fallback.xlsx",
        layout=make_layout(title=None, version=""),
        contract=make_contract(),
    )
    assert metrics["title"] == "fallback.xlsx"
    assert metrics["version"] is None


def test_build_description_metrics_returns_exact_dict():
    metrics = tasks_template_analysis._build_description_metrics(
        title="Invoice",
        version="v2",
        contract=make_contract(),
        description="Auto description",
    )

    assert metrics == {
        "title": "Invoice",
        "version": "v2",
        "field_count": 3,
        "scalar_field_count": 2,
        "table_field_count": 1,
        "description_text": "Auto description",
        "description_source": "llm_or_deterministic_fallback",
    }


@pytest.mark.parametrize(
    "row_kwargs,nodes,expected",
    [
        ({"status": " Archived "}, [], "archived"),
        ({"status": "ARCHIVED"}, [make_node("approval", "completed")], "archived"),
        (
            {"status": "approval_required", "_vector_status": "completed"},
            [make_node("approval", "completed")],
            "ready",
        ),
        (
            {"status": "approval_required", "_vector_status": "Done "},
            [
                make_node("approval", "completed"),
                make_node("schema", "completed"),
                make_node("description", "completed"),
            ],
            "ready",
        ),
        (
            {"status": "approval_required", "_vector_status": "pending"},
            [make_node("approval", "completed")],
            "uploaded",
        ),
        (
            {"status": "Uploaded"},
            [make_node("schema", "COMPLETED"), make_node("description", " Completed ")],
            "approval_required",
        ),
        ({"status": "approval_required"}, [make_node("schema", "completed")], "uploaded"),
        ({"status": ""}, [], "uploaded"),
        ({}, [make_node("other", "completed")], "uploaded"),
    ],
)
def test_resolve_template_status(row_kwargs, nodes, expected):
    assert tasks_template_analysis._resolve_template_status(dict(row_kwargs), nodes) == expected


async def test_update_analysis_node_passes_arguments_through():
    status_repo = SimpleNamespace(upsert_node=AsyncMock())
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    await tasks_template_analysis._update_analysis_node(
        status_repo=status_repo,
        collection_id=COLLECTION_UUID,
        row_id=ROW_UUID,
        node_key="schema",
        status="processing",
        started_at=started,
    )

    status_repo.upsert_node.assert_awaited_once_with(
        collection_id=COLLECTION_UUID,
        row_id=ROW_UUID,
        node_key="schema",
        status="processing",
        error_short=None,
        metrics_json=None,
        started_at=started,
        finished_at=None,
    )


# ---------------------------------------------------------------------------
# _run_with_context
# ---------------------------------------------------------------------------


async def test_run_with_context_passes_handles_to_handler(monkeypatch):
    collection = SimpleNamespace(id=COLLECTION_UUID)
    row = {"id": str(ROW_UUID)}
    ctx = install_run_context(monkeypatch, collection=collection, get_row_results=[row])

    async def handler(session, service, status_repo, collection_arg, row_arg):
        return (session, service, status_repo, collection_arg, row_arg)

    result = await tasks_template_analysis._run_with_context(str(COLLECTION_UUID), str(ROW_UUID), handler)

    session, service, status_repo, collection_arg, row_arg = result
    assert session is ctx.session
    assert service is ctx.instances[0]
    assert status_repo is ctx.status_repo
    assert collection_arg is collection
    assert row_arg is row

    ctx.get_by_id.assert_awaited_once_with(COLLECTION_UUID)
    ctx.ensure.assert_awaited_once_with(collection, ensure_vector_infra=False)
    ctx.get_row_by_id.assert_awaited_once_with(collection, ROW_UUID)


async def test_run_with_context_requires_collection(monkeypatch):
    ctx = install_run_context(monkeypatch, collection=None, get_row_results=[{"id": str(ROW_UUID)}])

    with pytest.raises(ValueError, match=f"Collection {COLLECTION_UUID} not found"):
        await tasks_template_analysis._run_with_context(str(COLLECTION_UUID), str(ROW_UUID), AsyncMock())

    ctx.ensure.assert_not_awaited()
    ctx.get_row_by_id.assert_not_awaited()


async def test_run_with_context_requires_row(monkeypatch):
    collection = SimpleNamespace(id=COLLECTION_UUID)
    ctx = install_run_context(monkeypatch, collection=collection, get_row_results=[None])

    with pytest.raises(ValueError, match=f"Template row {ROW_UUID} not found"):
        await tasks_template_analysis._run_with_context(str(COLLECTION_UUID), str(ROW_UUID), AsyncMock())

    ctx.ensure.assert_awaited_once_with(collection, ensure_vector_infra=False)
    ctx.get_row_by_id.assert_awaited_once_with(collection, ROW_UUID)


# ---------------------------------------------------------------------------
# _load_template_file
# ---------------------------------------------------------------------------


async def test_load_template_file_rejects_non_dict_metadata():
    with pytest.raises(ValueError, match="Template file metadata is missing"):
        await tasks_template_analysis._load_template_file({"file": "corrupt"})


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"file": None},
        {"file": {}},
        {"file": {"bucket": "   ", "s3_key": "k"}},
        {"file": {"bucket": "b", "s3_key": ""}},
    ],
)
async def test_load_template_file_rejects_incomplete_metadata(row):
    with pytest.raises(ValueError, match="Template file metadata is incomplete"):
        await tasks_template_analysis._load_template_file(row)


async def test_load_template_file_fails_when_s3_object_missing(monkeypatch):
    manager = install_s3(monkeypatch, None)

    with pytest.raises(ValueError, match="Failed to load template file s3://bucket/key.xlsx"):
        await tasks_template_analysis._load_template_file({"file": {"bucket": "bucket", "s3_key": "key.xlsx"}})

    manager.get_object.assert_awaited_once_with(bucket="bucket", key="key.xlsx")


@pytest.mark.parametrize(
    "file_meta,expected_filename",
    [
        ({"bucket": " b ", "s3_key": " dir/x.xlsx ", "filename": " x.xlsx "}, "x.xlsx"),
        ({"bucket": "b", "s3_key": "dir/x.xlsx"}, "template.bin"),
    ],
)
async def test_load_template_file_returns_payload_and_filename(monkeypatch, file_meta, expected_filename):
    manager = install_s3(monkeypatch, b"bytes")

    payload, filename = await tasks_template_analysis._load_template_file({"file": dict(file_meta)})

    assert payload == b"bytes"
    assert filename == expected_filename
    manager.get_object.assert_awaited_once_with(
        bucket=file_meta["bucket"].strip(),
        key=file_meta["s3_key"].strip(),
    )


# ---------------------------------------------------------------------------
# _publish_snapshot
# ---------------------------------------------------------------------------


def make_status_repo(nodes) -> SimpleNamespace:
    return SimpleNamespace(get_nodes_by_row_id=AsyncMock(return_value=list(nodes)))


async def test_publish_snapshot_skips_without_redis(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL=""))
    from_url = Mock()
    monkeypatch.setattr("redis.asyncio.from_url", from_url)
    status_repo = make_status_repo([])

    await tasks_template_analysis._publish_snapshot(
        collection_id="tpl-1",
        collection_uuid=COLLECTION_UUID,
        row={"id": str(ROW_UUID), "has_vector_search": True},
        status_repo=status_repo,
    )

    from_url.assert_not_called()
    status_repo.get_nodes_by_row_id.assert_not_awaited()


async def test_publish_snapshot_publishes_row_and_collection_payloads(monkeypatch):
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    nodes = [
        SimpleNamespace(
            node_key="description",
            status="completed",
            error_short=None,
            metrics_json={"a": 1},
            started_at=started,
            finished_at=None,
        )
    ]
    serialized = tasks_template_analysis._serialize_analysis_nodes(nodes)
    status_repo = make_status_repo(nodes)

    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL="redis://test:6379/1"))
    fake_client = SimpleNamespace(aclose=AsyncMock())
    from_url = Mock(return_value=fake_client)
    monkeypatch.setattr("redis.asyncio.from_url", from_url)

    publishers: list = []

    class FakePublisher:
        def __init__(self, client) -> None:
            self.client = client
            self.publish_snapshot = AsyncMock()
            self.publish_collection_snapshot = AsyncMock()
            publishers.append(self)

    monkeypatch.setattr(tasks_template_analysis, "TemplateStatusPublisher", FakePublisher)
    row_payload = Mock(return_value={"row": "payload"})
    graph_payload = Mock(return_value={"graph": "payload"})
    monkeypatch.setattr(tasks_template_analysis, "build_template_row_runtime_payload", row_payload)
    monkeypatch.setattr(tasks_template_analysis, "build_template_status_graph", graph_payload)

    await tasks_template_analysis._publish_snapshot(
        collection_id="tpl-1",
        collection_uuid=COLLECTION_UUID,
        row={"id": str(ROW_UUID), "has_vector_search": 1},
        status_repo=status_repo,
    )

    from_url.assert_called_once_with("redis://test:6379/1", decode_responses=True)
    status_repo.get_nodes_by_row_id.assert_awaited_once_with(ROW_UUID)
    row_payload.assert_called_once_with(
        {"id": str(ROW_UUID), "has_vector_search": True},
        collection_id="tpl-1",
        analysis_nodes=serialized,
    )
    graph_payload.assert_called_once_with(
        {"row": "payload"},
        collection_id="tpl-1",
        analysis_nodes=serialized,
    )

    assert len(publishers) == 1
    assert publishers[0].client is fake_client
    publishers[0].publish_snapshot.assert_awaited_once_with(row_id=ROW_UUID, payload={"graph": "payload"})
    publishers[0].publish_collection_snapshot.assert_awaited_once_with(
        collection_id=COLLECTION_UUID,
        row_id=ROW_UUID,
        payload={"row": "payload"},
    )
    fake_client.aclose.assert_awaited_once_with()


async def test_publish_snapshot_swallows_aclose_errors(monkeypatch):
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL="redis://test:6379/1"))
    fake_client = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    monkeypatch.setattr("redis.asyncio.from_url", Mock(return_value=fake_client))

    class FakePublisher:
        def __init__(self, client) -> None:
            self.publish_snapshot = AsyncMock()
            self.publish_collection_snapshot = AsyncMock()

    monkeypatch.setattr(tasks_template_analysis, "TemplateStatusPublisher", FakePublisher)
    monkeypatch.setattr(
        tasks_template_analysis,
        "build_template_row_runtime_payload",
        Mock(return_value={"row": "payload"}),
    )
    monkeypatch.setattr(
        tasks_template_analysis,
        "build_template_status_graph",
        Mock(return_value={"graph": "payload"}),
    )
    status_repo = make_status_repo([])

    await tasks_template_analysis._publish_snapshot(
        collection_id="tpl-1",
        collection_uuid=COLLECTION_UUID,
        row={"id": str(ROW_UUID)},
        status_repo=status_repo,
    )


# ---------------------------------------------------------------------------
# generate_template_description
# ---------------------------------------------------------------------------


def test_generate_template_description_success(monkeypatch):
    contract = make_contract()
    row = {
        "id": str(ROW_UUID),
        "status": "uploaded",
        "title": "Invoice",
        "template_version": "v2",
        "template_schema": contract.to_jsonb(),
    }
    final_row = {**row, "status": "approval_required"}
    collection = SimpleNamespace(id=COLLECTION_UUID, has_vector_search=True)
    ctx = install_run_context(
        monkeypatch,
        collection=collection,
        get_row_results=[row, final_row],
        update_results=[{**row}, final_row],
        nodes=[make_node("schema", "completed"), make_node("description", "completed")],
    )

    publish = AsyncMock()
    monkeypatch.setattr(tasks_template_analysis, "_publish_snapshot", publish)
    llm_client = object()
    monkeypatch.setattr("app.core.di.get_llm_client", lambda: llm_client)
    builders = install_description_builder(monkeypatch, "Auto description")

    result = tasks_template_analysis.generate_template_description.run(str(COLLECTION_UUID), str(ROW_UUID))

    assert result == {
        "status": "ok",
        "collection_id": str(COLLECTION_UUID),
        "row_id": str(ROW_UUID),
        "template_status": "approval_required",
        "vectorization_task_id": None,
    }
    assert len(builders) == 1
    assert builders[0].llm is llm_client
    assert builders[0].build.await_args.kwargs == {"title": "Invoice", "version": "v2"}
    built_contract = builders[0].build.await_args.args[0]
    assert isinstance(built_contract, TemplateContract)
    assert [field.key for field in built_contract.fields] == ["title_field", "date_field", "items"]

    upserts = ctx.status_repo.upsert_node.await_args_list
    assert len(upserts) == 2
    first = upserts[0].kwargs
    assert first["node_key"] == "description"
    assert first["status"] == "processing"
    assert first["collection_id"] == COLLECTION_UUID
    assert first["row_id"] == ROW_UUID
    assert isinstance(first["started_at"], datetime)
    assert first["finished_at"] is None
    second = upserts[1].kwargs
    assert second["node_key"] == "description"
    assert second["status"] == "completed"
    assert second["metrics_json"] == {
        "title": "Invoice",
        "version": "v2",
        "field_count": 3,
        "scalar_field_count": 2,
        "table_field_count": 1,
        "description_text": "Auto description",
        "description_source": "llm_or_deterministic_fallback",
    }
    assert isinstance(second["finished_at"], datetime)
    assert second["started_at"] is None

    assert ctx.update_row.await_args_list == [
        call(
            collection,
            ROW_UUID,
            {"title": "Invoice", "template_version": "v2", "description": "Auto description"},
            skip_vectorization=True,
        ),
        call(collection, ROW_UUID, {"status": "approval_required"}, skip_vectorization=True),
    ]
    assert ctx.session.commit.await_count == 3
    assert ctx.get_row_by_id.await_count == 2
    ctx.status_repo.get_nodes_by_row_id.assert_awaited_once_with(ROW_UUID)
    publish.assert_awaited_once_with(
        collection_id=str(COLLECTION_UUID),
        collection_uuid=COLLECTION_UUID,
        row={**final_row, "has_vector_search": True},
        status_repo=ctx.status_repo,
    )


def test_generate_template_description_failure_marks_node_failed_and_retries(monkeypatch):
    row = {
        "id": str(ROW_UUID),
        "status": "uploaded",
        "title": "Invoice",
        "template_schema": {},
    }
    collection = SimpleNamespace(id=COLLECTION_UUID, has_vector_search=False)
    ctx = install_run_context(
        monkeypatch,
        collection=collection,
        get_row_results=[row, row],
        update_results=None,
        nodes=[],
    )
    publish = AsyncMock()
    monkeypatch.setattr(tasks_template_analysis, "_publish_snapshot", publish)
    attempts = install_retry(monkeypatch, tasks_template_analysis.generate_template_description)

    with pytest.raises(ValueError, match="Template schema is not ready; run schema analysis before description"):
        tasks_template_analysis.generate_template_description.run(str(COLLECTION_UUID), str(ROW_UUID))

    assert len(attempts) == 1
    assert isinstance(attempts[0], ValueError)
    assert ctx.session.commit.await_count == 2
    ctx.update_row.assert_not_awaited()
    ctx.status_repo.get_nodes_by_row_id.assert_not_awaited()

    upserts = ctx.status_repo.upsert_node.await_args_list
    assert len(upserts) == 2
    failed = upserts[1].kwargs
    assert failed["node_key"] == "description"
    assert failed["status"] == "failed"
    assert failed["error_short"] == "Template schema is not ready; run schema analysis before description"
    assert isinstance(failed["finished_at"], datetime)

    publish.assert_awaited_once_with(
        collection_id=str(COLLECTION_UUID),
        collection_uuid=COLLECTION_UUID,
        row={**row, "has_vector_search": False},
        status_repo=ctx.status_repo,
    )


# ---------------------------------------------------------------------------
# generate_template_schema
# ---------------------------------------------------------------------------


def test_generate_template_schema_success(monkeypatch):
    contract = make_contract()
    layout = make_layout()
    row = {
        "id": str(ROW_UUID),
        "status": "uploaded",
        "title": "Old title",
        "template_version": "v1",
        "template_schema": {},
        "file": {
            "bucket": "tpl",
            "s3_key": "dir/invoice.xlsx",
            "filename": " invoice.xlsx ",
            "content_type": "spreadsheet",
            "size": 1234,
        },
    }
    final_row = {**row, "title": "Invoice", "template_version": "v2", "template_schema": contract.to_jsonb()}
    collection = SimpleNamespace(id=COLLECTION_UUID, has_vector_search=False)
    ctx = install_run_context(
        monkeypatch,
        collection=collection,
        get_row_results=[row, final_row],
        update_results=[final_row],
        nodes=[make_node("schema", "completed")],
    )
    manager = install_s3(monkeypatch, b"file-bytes")
    parsers = install_layout_parser(monkeypatch, layout)
    builders = install_schema_builder(monkeypatch, contract)
    orchestrator = install_orchestrator(monkeypatch, "task-abc")
    publish = AsyncMock()
    monkeypatch.setattr(tasks_template_analysis, "_publish_snapshot", publish)

    result = tasks_template_analysis.generate_template_schema.run(str(COLLECTION_UUID), str(ROW_UUID))

    assert result == {
        "status": "ok",
        "collection_id": str(COLLECTION_UUID),
        "row_id": str(ROW_UUID),
        "template_status": "uploaded",
        "description_task_id": "task-abc",
    }
    manager.get_object.assert_awaited_once_with(bucket="tpl", key="dir/invoice.xlsx")
    parsers[0].parse.assert_called_once_with(b"file-bytes", "invoice.xlsx")
    assert builders[0].llm is None
    build_kwargs = builders[0].build.await_args.kwargs
    assert builders[0].build.await_args.args == (layout,)
    assert isinstance(build_kwargs["existing_contract"], TemplateContract)
    assert build_kwargs["existing_contract"].fields == []
    assert build_kwargs["title"] == "Invoice"
    orchestrator.enqueue_description.assert_called_once_with(
        collection_id=COLLECTION_UUID,
        row_id=ROW_UUID,
        countdown=1,
    )

    ctx.update_row.assert_awaited_once_with(
        collection,
        ROW_UUID,
        {
            "title": "Invoice",
            "template_version": "v2",
            "template_schema": contract.to_jsonb(),
        },
        skip_vectorization=True,
    )
    assert ctx.session.commit.await_count == 3
    assert ctx.get_row_by_id.await_count == 2
    ctx.status_repo.get_nodes_by_row_id.assert_awaited_once_with(ROW_UUID)

    upserts = ctx.status_repo.upsert_node.await_args_list
    assert len(upserts) == 2
    assert upserts[0].kwargs["node_key"] == "schema"
    assert upserts[0].kwargs["status"] == "processing"
    assert isinstance(upserts[0].kwargs["started_at"], datetime)
    completed = upserts[1].kwargs
    assert completed["node_key"] == "schema"
    assert completed["status"] == "completed"
    assert completed["metrics_json"]["filename"] == "invoice.xlsx"
    assert completed["metrics_json"]["schema_summary"] == "3 fields, 1 tables"
    assert isinstance(completed["finished_at"], datetime)

    publish.assert_awaited_once_with(
        collection_id=str(COLLECTION_UUID),
        collection_uuid=COLLECTION_UUID,
        row={**final_row, "has_vector_search": False},
        status_repo=ctx.status_repo,
    )


def test_generate_template_schema_updates_status_when_analysis_completes(monkeypatch):
    contract = make_contract()
    layout = make_layout()
    row = {
        "id": str(ROW_UUID),
        "status": "uploaded",
        "title": "Old title",
        "template_version": "v1",
        "template_schema": {},
        "file": {"bucket": "tpl", "s3_key": "dir/invoice.xlsx", "filename": "invoice.xlsx"},
    }
    after_schema = {
        **row,
        "title": "Invoice",
        "template_version": "v2",
        "template_schema": contract.to_jsonb(),
    }
    after_status = {**after_schema, "status": "approval_required"}
    collection = SimpleNamespace(id=COLLECTION_UUID, has_vector_search=False)
    ctx = install_run_context(
        monkeypatch,
        collection=collection,
        get_row_results=[row, after_status],
        update_results=[after_schema, after_status],
        nodes=[make_node("schema", "completed"), make_node("description", "completed")],
    )
    install_s3(monkeypatch, b"file-bytes")
    install_layout_parser(monkeypatch, layout)
    install_schema_builder(monkeypatch, contract)
    install_orchestrator(monkeypatch, "task-def")
    publish = AsyncMock()
    monkeypatch.setattr(tasks_template_analysis, "_publish_snapshot", publish)

    result = tasks_template_analysis.generate_template_schema.run(str(COLLECTION_UUID), str(ROW_UUID))

    assert result["template_status"] == "approval_required"
    assert ctx.update_row.await_count == 2
    ctx.update_row.assert_any_await(
        collection,
        ROW_UUID,
        {"status": "approval_required"},
        skip_vectorization=True,
    )
    assert ctx.session.commit.await_count == 4
    assert ctx.get_row_by_id.await_count == 2
    publish.assert_awaited_once_with(
        collection_id=str(COLLECTION_UUID),
        collection_uuid=COLLECTION_UUID,
        row={**after_status, "has_vector_search": False},
        status_repo=ctx.status_repo,
    )


def test_generate_template_schema_failure_marks_node_failed_and_retries(monkeypatch):
    row = {
        "id": str(ROW_UUID),
        "status": "uploaded",
        "file": {"bucket": "tpl", "s3_key": "key.xlsx"},
    }
    collection = SimpleNamespace(id=COLLECTION_UUID, has_vector_search=False)
    ctx = install_run_context(
        monkeypatch,
        collection=collection,
        get_row_results=[row, row],
        update_results=None,
        nodes=[],
    )
    install_s3(monkeypatch, None)
    publish = AsyncMock()
    monkeypatch.setattr(tasks_template_analysis, "_publish_snapshot", publish)
    attempts = install_retry(monkeypatch, tasks_template_analysis.generate_template_schema)

    with pytest.raises(ValueError, match="Failed to load template file s3://tpl/key.xlsx"):
        tasks_template_analysis.generate_template_schema.run(str(COLLECTION_UUID), str(ROW_UUID))

    assert len(attempts) == 1
    assert isinstance(attempts[0], ValueError)
    assert ctx.session.commit.await_count == 2
    ctx.update_row.assert_not_awaited()
    ctx.status_repo.get_nodes_by_row_id.assert_not_awaited()

    upserts = ctx.status_repo.upsert_node.await_args_list
    assert len(upserts) == 2
    failed = upserts[1].kwargs
    assert failed["node_key"] == "schema"
    assert failed["status"] == "failed"
    assert failed["error_short"] == "Failed to load template file s3://tpl/key.xlsx"
    assert isinstance(failed["finished_at"], datetime)

    publish.assert_awaited_once_with(
        collection_id=str(COLLECTION_UUID),
        collection_uuid=COLLECTION_UUID,
        row={**row, "has_vector_search": False},
        status_repo=ctx.status_repo,
    )
