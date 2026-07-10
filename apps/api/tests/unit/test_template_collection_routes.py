from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.routers.collections import templates as templates_router
from app.services import collection_service as collection_service_module
from app.services.collection.template_status_stream import (
    build_template_row_runtime_payload,
    build_template_status_graph,
)


@pytest.mark.asyncio
async def test_upload_template_uses_safe_log_keys(monkeypatch):
    collection_id = uuid4()
    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=uuid4(),
        collection_type="template",
    )
    monkeypatch.setattr(templates_router, "_resolve_template_collection", AsyncMock(return_value=fake_collection))

    fake_collection_service = MagicMock()
    fake_collection_service.ensure_contract_fields_present = AsyncMock(return_value=None)
    monkeypatch.setattr(collection_service_module, "CollectionService", lambda _session: fake_collection_service)

    fake_upload_service = MagicMock()
    fake_upload_service.upload_template = AsyncMock(
        return_value={
            "row_id": "row-1",
            "collection_id": str(collection_id),
            "file_id": "file-1",
            "title": "template.xlsx",
            "source": "s3://bucket/key",
            "status": "uploaded",
            "message": "Template uploaded successfully",
        }
    )
    monkeypatch.setattr(templates_router, "TemplateUploadService", lambda _session: fake_upload_service)

    fake_snapshot_service = MagicMock()
    fake_snapshot_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(templates_router, "CollectionStatusSnapshotService", lambda _session: fake_snapshot_service)
    monkeypatch.setattr(templates_router, "TemplateAnalysisOrchestrator", SimpleNamespace(enqueue_all=MagicMock(return_value={})))

    file = SimpleNamespace(
        filename="template.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        read=AsyncMock(return_value=b"binary"),
    )
    session = AsyncMock()
    user = SimpleNamespace(id=uuid4(), role="admin", tenant_ids=[])

    result = await templates_router.upload_template(
        collection_id=collection_id,
        file=file,
        session=session,
        user=user,
    )

    assert result["row_id"] == "row-1"
    fake_collection_service.ensure_contract_fields_present.assert_awaited_once_with(fake_collection, ensure_vector_infra=True)
    fake_upload_service.upload_template.assert_awaited_once()
    fake_snapshot_service.sync_collection_status.assert_awaited_once_with(fake_collection, persist=False)


@pytest.mark.asyncio
async def test_delete_templates_deletes_rows_and_refreshes_status(monkeypatch):
    collection_id = uuid4()
    row_ids = [uuid4(), uuid4()]

    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=uuid4(),
        collection_type="template",
    )
    resolve_mock = AsyncMock(return_value=fake_collection)
    monkeypatch.setattr(templates_router, "_resolve_template_collection", resolve_mock)

    fake_row_service = MagicMock()
    fake_row_service.delete_rows = AsyncMock(return_value=len(row_ids))
    monkeypatch.setattr(templates_router, "CollectionRowService", lambda _session: fake_row_service)

    fake_snapshot_service = MagicMock()
    fake_snapshot_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(
        templates_router,
        "CollectionStatusSnapshotService",
        lambda _session: fake_snapshot_service,
    )

    session = AsyncMock()
    result = await templates_router.delete_templates(
        collection_id=collection_id,
        ids=row_ids,
        session=session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    resolve_mock.assert_awaited_once()
    fake_row_service.delete_rows.assert_awaited_once_with(fake_collection, row_ids)
    fake_snapshot_service.sync_collection_status.assert_awaited_once_with(fake_collection, persist=False)
    session.commit.assert_awaited_once()
    assert result == {
        "deleted": 2,
        "ids": [str(row_id) for row_id in row_ids],
    }


def test_build_template_runtime_payload_moves_to_approval_after_description():
    payload = build_template_row_runtime_payload(
        {
            "id": str(uuid4()),
            "status": "analyzed",
            "description": "semantic",
            "template_schema": {"fields": [{"key": "name"}]},
            "has_vector_search": True,
            "_vector_status": "pending",
        },
        collection_id=str(uuid4()),
        analysis_nodes=[
            {"node_key": "schema", "status": "completed", "metrics_json": {}},
            {"node_key": "description", "status": "completed", "metrics_json": {}},
        ],
    )

    assert payload["runtime_status"] == "approval_required"
    assert payload["runtime_stage"] == "approval"
    assert payload["approval_required"] is True


def test_build_template_status_graph_surfaces_failed_schema_stage():
    graph = build_template_status_graph(
        {
            "id": str(uuid4()),
            "status": "uploaded",
            "file": {
                "filename": "template.xlsx",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 1024,
            },
            "has_vector_search": False,
        },
        collection_id=str(uuid4()),
        analysis_nodes=[
            {
                "node_key": "schema",
                "status": "failed",
                "error_short": "schema boom",
                "metrics_json": {"format": "excel", "sheet_count": 2, "sheet_names": ["Main", "Meta"]},
                "started_at": "2026-01-01T10:00:00+00:00",
                "finished_at": "2026-01-01T10:00:10+00:00",
            },
        ],
    )

    assert graph["runtime_status"] == "failed"
    assert graph["runtime_stage"] == "schema"
    uploaded_stage = next(stage for stage in graph["stages"] if stage["key"] == "uploaded")
    assert uploaded_stage["metrics"]["filename"] == "template.xlsx"
    assert uploaded_stage["metrics"]["sheet_count"] == 2
    schema_stage = next(stage for stage in graph["stages"] if stage["key"] == "schema")
    assert schema_stage["state"] == "failed"
    assert schema_stage["error"] == "schema boom"
    assert schema_stage["started_at"] == "2026-01-01T10:00:00+00:00"
    assert graph["analysis_nodes"]["schema"]["started_at"] == "2026-01-01T10:00:00+00:00"


def test_build_template_runtime_payload_tracks_vectorization_and_indexing_separately():
    payload = build_template_row_runtime_payload(
        {
            "id": str(uuid4()),
            "status": "analyzed",
            "description": "semantic",
            "template_schema": {"fields": [{"key": "name"}]},
            "has_vector_search": True,
            "_vector_status": "pending",
        },
        collection_id=str(uuid4()),
        analysis_nodes=[
            {"node_key": "schema", "status": "completed", "metrics_json": {}},
            {"node_key": "description", "status": "completed", "metrics_json": {}},
            {"node_key": "approval", "status": "completed", "metrics_json": {}},
            {"node_key": "vectorization", "status": "completed", "metrics_json": {}},
            {"node_key": "indexing", "status": "processing", "metrics_json": {}},
        ],
    )

    assert payload["runtime_status"] == "processing"
    assert payload["runtime_stage"] == "indexing"
    assert payload["vectorization_status"] == "completed"
    assert payload["indexing_status"] == "processing"


def test_build_template_status_graph_surfaces_indexing_failure_stage():
    graph = build_template_status_graph(
        {
            "id": str(uuid4()),
            "status": "analyzed",
            "description": "semantic",
            "template_schema": {"fields": [{"key": "name"}]},
            "has_vector_search": True,
        },
        collection_id=str(uuid4()),
        analysis_nodes=[
            {"node_key": "schema", "status": "completed", "metrics_json": {}},
            {"node_key": "description", "status": "completed", "metrics_json": {}},
            {"node_key": "approval", "status": "completed", "metrics_json": {}},
            {"node_key": "vectorization", "status": "completed", "metrics_json": {}},
            {"node_key": "indexing", "status": "failed", "error_short": "index boom", "metrics_json": {}},
        ],
    )

    assert graph["runtime_status"] == "failed"
    assert graph["runtime_stage"] == "indexing"
    indexing_stage = next(stage for stage in graph["stages"] if stage["key"] == "indexing")
    assert indexing_stage["state"] == "failed"
    assert indexing_stage["error"] == "index boom"


@pytest.mark.asyncio
async def test_approve_template_marks_node_and_enqueues_vectorization(monkeypatch):
    collection_id = uuid4()
    row_id = uuid4()
    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=uuid4(),
        collection_type="template",
        has_vector_search=True,
        table_name="coll_template",
    )
    resolve_mock = AsyncMock(return_value=fake_collection)
    monkeypatch.setattr(templates_router, "_resolve_template_collection", resolve_mock)

    fake_row_service = MagicMock()
    fake_row_service.get_row_by_id = AsyncMock(
        side_effect=[
            {"id": str(row_id), "status": "analyzed", "description": "desc", "template_schema": {"fields": [{"key": "a"}]}},
            {"id": str(row_id), "status": "analyzed", "description": "desc", "template_schema": {"fields": [{"key": "a"}]}},
        ]
    )
    fake_row_service.update_row = AsyncMock(return_value={"id": str(row_id), "status": "analyzed"})
    monkeypatch.setattr(templates_router, "CollectionRowService", lambda _session: fake_row_service)

    fake_status_repo = MagicMock()
    fake_status_repo.get_nodes_by_row_id = AsyncMock(return_value=[
        SimpleNamespace(node_key="schema", status="completed", error_short=None, metrics_json={}, finished_at=None),
        SimpleNamespace(node_key="description", status="completed", error_short=None, metrics_json={}, finished_at=None),
    ])
    fake_status_repo.upsert_node = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(templates_router, "AsyncTemplateAnalysisStatusRepository", lambda _session: fake_status_repo)

    fake_snapshot_service = MagicMock()
    fake_snapshot_service.sync_collection_status = AsyncMock(return_value=None)
    monkeypatch.setattr(templates_router, "CollectionStatusSnapshotService", lambda _session: fake_snapshot_service)
    monkeypatch.setattr(
        templates_router,
        "_load_template_runtime_rows",
        AsyncMock(return_value=[{"id": str(row_id), "runtime_status": "processing"}]),
    )
    enqueue_mock = MagicMock(return_value="vec-task-1")
    monkeypatch.setattr(
        templates_router,
        "CollectionVectorizationOrchestrator",
        SimpleNamespace(enqueue=enqueue_mock),
    )

    session = AsyncMock()
    result = await templates_router.approve_template(
        collection_id=collection_id,
        row_id=row_id,
        data=templates_router.ApproveTemplateRequest(),
        session=session,
        user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
    )

    fake_status_repo.upsert_node.assert_awaited_once()
    fake_row_service.update_row.assert_awaited_once()
    enqueue_mock.assert_called_once()
    session.commit.assert_awaited_once()
    assert result["vectorization_task_id"] == "vec-task-1"


@pytest.mark.asyncio
async def test_analyze_templates_rejects_legacy_xls(monkeypatch):
    collection_id = uuid4()
    row_id = uuid4()
    fake_collection = SimpleNamespace(
        id=collection_id,
        tenant_id=uuid4(),
        collection_type="template",
    )
    monkeypatch.setattr(templates_router, "_resolve_template_collection", AsyncMock(return_value=fake_collection))

    fake_row_service = MagicMock()
    fake_row_service.get_row_by_id = AsyncMock(
        return_value={
            "id": str(row_id),
            "file": {"filename": "legacy.xls"},
        }
    )
    monkeypatch.setattr(templates_router, "CollectionRowService", lambda _session: fake_row_service)
    monkeypatch.setattr(templates_router, "AsyncTemplateAnalysisStatusRepository", lambda _session: MagicMock())

    with pytest.raises(templates_router.HTTPException) as exc_info:
        await templates_router.analyze_templates(
            collection_id=collection_id,
            data=templates_router.AnalyzeTemplatesRequest(row_ids=[row_id]),
            session=AsyncMock(),
            user=SimpleNamespace(id=str(uuid4()), role="admin", tenant_ids=[]),
        )
    assert "legacy .xls" in str(exc_info.value.detail)
