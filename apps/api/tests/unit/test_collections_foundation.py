from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.agents.builtins.collection_aggregate import CollectionAggregateTool
from app.agents.builtins.collection_doc_search import CollectionDocSearchTool
from app.agents.builtins.collection_search import CollectionSearchTool
from app.agents.builtins.collection_text_search import CollectionTextSearchTool
from app.models.collection import Collection, CollectionType, FieldCategory, FieldType
from app.schemas.collections import SchemaOperation, UpdateCollectionRequest
from app.services.document_artifacts import (
    build_document_source_meta,
    get_document_artifact_key,
    normalize_document_source_meta,
    upsert_document_artifact,
)
from app.services.collection_service import CollectionService, InvalidSchemaError, RowValidationError
from app.services.collection.row_service import CollectionRowService
from app.workers.tasks_collection_vectorize import _build_point_id


def _table_collection() -> Collection:
    return Collection(
        id=uuid4(),
        data_instance_id=uuid4(),
        tenant_id=uuid4(),
        collection_type=CollectionType.TABLE.value,
        slug="tickets",
        name="Tickets",
        description="Test collection",
        table_name="coll_test_tickets",
        fields=[
            {
                "name": "title",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": True,
                "description": "Title",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            },
            {
                "name": "priority",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.INTEGER.value,
                "required": False,
                "description": "Priority",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "opened_at",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.DATETIME.value,
                "required": False,
                "description": "Opened at",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "meta",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.JSON.value,
                "required": False,
                "description": "Meta",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
        ],
        status="ready",
        total_rows=0,
        vectorized_rows=0,
        total_chunks=0,
        failed_rows=0,
        is_active=True,
        allow_unfiltered_search=False,
        max_limit=100,
        query_timeout_seconds=10,
    )


def test_collection_search_in_and_not_in_expand_placeholders():
    tool = CollectionSearchTool()

    sql_in, params_in, _ = tool._build_condition(  # noqa: SLF001
        {"field": "priority", "op": "in", "value": [1, 2, 3]},
        {},
        0,
    )
    assert sql_in == "priority IN (:p0_0, :p0_1, :p0_2)"
    assert params_in == {"p0_0": 1, "p0_1": 2, "p0_2": 3}

    sql_not_in, params_not_in, _ = tool._build_condition(  # noqa: SLF001
        {"field": "priority", "op": "not_in", "value": [4, 5]},
        {},
        1,
    )
    assert sql_not_in == "priority NOT IN (:p1_0, :p1_1)"
    assert params_not_in == {"p1_0": 4, "p1_1": 5}


def test_collection_aggregate_rejects_non_filterable_field():
    tool = CollectionAggregateTool()
    collection = _table_collection()

    error = tool._validate_filters(  # noqa: SLF001
        collection,
        {"and": [{"field": "meta", "op": "eq", "value": "x"}]},
    )

    assert error == "Unknown or non-filterable field 'meta' in filter"


def test_collection_aggregate_rejects_invalid_time_bucket_field():
    tool = CollectionAggregateTool()
    collection = _table_collection()

    error = tool._validate_time_bucket(  # noqa: SLF001
        collection,
        {"field": "title", "interval": "day"},
    )

    assert error == "time_bucket field 'title' must be date/datetime"


def test_collection_aggregate_rejects_invalid_order_by():
    tool = CollectionAggregateTool()
    collection = _table_collection()

    error = tool._validate_order_by(  # noqa: SLF001
        collection,
        metrics=[{"function": "count", "alias": "metric_0"}],
        group_by=["priority"],
        time_bucket=None,
        order_by="meta",
    )

    assert error == "Invalid order_by field 'meta'"


def test_collection_aggregate_in_operator_expands_placeholders():
    tool = CollectionAggregateTool()

    sql, params, _ = tool._build_condition(  # noqa: SLF001
        {"field": "priority", "op": "in", "value": [1, 2]},
        {},
        0,
    )

    assert sql == "priority IN (:p0_0, :p0_1)"
    assert params == {"p0_0": 1, "p0_1": 2}


def test_document_source_meta_normalizes_legacy_shape():
    meta = normalize_document_source_meta(
        {
            "filename": "doc.txt",
            "title": "Doc",
            "content_type": "text/plain",
            "size": 42,
            "s3_key": "tenant/doc/original/doc.txt",
            "canonical_key": "tenant/doc/canonical/doc.json",
            "chunks_key": "tenant/doc/chunks/doc.jsonl",
            "collection_id": "collection-1",
            "collection_row_id": "row-1",
            "qdrant_collection_name": "qdrant-1",
            "chunk_strategy": "by_paragraphs",
        }
    )

    assert meta["document"]["filename"] == "doc.txt"
    assert meta["document"]["size_bytes"] == 42
    assert meta["collection"]["id"] == "collection-1"
    assert meta["collection"]["row_id"] == "row-1"
    assert meta["artifacts"]["original"]["key"] == "tenant/doc/original/doc.txt"
    assert meta["artifacts"]["canonical"]["key"] == "tenant/doc/canonical/doc.json"
    assert meta["artifacts"]["chunks"]["key"] == "tenant/doc/chunks/doc.jsonl"
    assert meta["chunk_strategy"] == "by_paragraphs"
    assert "s3_key" not in meta
    assert "collection_id" not in meta


def test_document_source_meta_build_and_upsert_artifacts():
    meta = build_document_source_meta(
        filename="policy.pdf",
        title="Policy",
        content_type="application/pdf",
        size_bytes=128,
        original_key="tenant/doc/original/policy.pdf",
        collection_id="collection-1",
        row_id="row-1",
        qdrant_collection_name="qdrant-1",
        source="kb",
        scope="security",
        tags=["policy"],
    )

    meta = upsert_document_artifact(
        meta,
        "canonical",
        {
            "key": "tenant/doc/canonical/policy.json",
            "checksum": "abc123",
        },
    )

    assert meta["document"]["source"] == "kb"
    assert meta["document"]["scope"] == "security"
    assert meta["document"]["tags"] == ["policy"]
    assert get_document_artifact_key(meta, "original") == "tenant/doc/original/policy.pdf"
    assert get_document_artifact_key(meta, "canonical") == "tenant/doc/canonical/policy.json"


def test_table_vector_point_id_is_deterministic():
    point_a = _build_point_id("collection-1", "row-1", "title", 0)
    point_b = _build_point_id("collection-1", "row-1", "title", 0)
    point_c = _build_point_id("collection-1", "row-1", "body", 0)

    assert point_a == point_b
    assert point_a != point_c


def test_collection_text_search_skips_stale_vector_hits_without_rows():
    tool = CollectionTextSearchTool()
    collection = _table_collection()

    sorted_rows = [
        {
            "row_id": "missing-row",
            "score": 0.9,
            "primary_field": "title",
            "primary_fragment": "stale hit",
            "matched_fields": {"title"},
            "matched_fragments": ["stale hit"],
        },
        {
            "row_id": "present-row",
            "score": 0.8,
            "primary_field": "title",
            "primary_fragment": "fresh hit",
            "matched_fields": {"title"},
            "matched_fragments": ["fresh hit"],
        },
    ]
    full_rows = {"present-row": {"title": "Fresh row"}}

    hits = []
    for row in sorted_rows:
        row_data = full_rows.get(row["row_id"])
        if not row_data:
            continue
        hits.append(
            {
                "row_id": row["row_id"],
                "score": round(row["score"], 3),
                "matched_fields": sorted(row["matched_fields"]),
                "matched_fragments": row["matched_fragments"],
                "primary_field": row["primary_field"],
                "primary_fragment": row["primary_fragment"],
                "row_data": row_data,
            }
        )

    assert hits == [
        {
            "row_id": "present-row",
            "score": 0.8,
            "matched_fields": ["title"],
            "matched_fragments": ["fresh hit"],
            "primary_field": "title",
            "primary_fragment": "fresh hit",
            "row_data": {"title": "Fresh row"},
        }
    ]


def test_collection_field_layers_hide_system_and_limit_business_fields():
    collection = Collection(
        id=uuid4(),
        data_instance_id=uuid4(),
        tenant_id=uuid4(),
        collection_type=CollectionType.DOCUMENT.value,
        slug="docs",
        name="Docs",
        description="Document collection",
        table_name="coll_test_docs",
        fields=[
            {
                "name": "file",
                "category": FieldCategory.SPECIFIC.value,
                "data_type": FieldType.FILE.value,
                "required": True,
                "description": "File ref",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
            {
                "name": "file_name",
                "category": FieldCategory.SPECIFIC.value,
                "data_type": FieldType.TEXT.value,
                "required": True,
                "description": "File name",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
            {
                "name": "title",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": False,
                "description": "Title",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            },
        ],
        status="ready",
        total_rows=0,
        vectorized_rows=0,
        total_chunks=0,
        failed_rows=0,
        is_active=True,
        allow_unfiltered_search=False,
        max_limit=100,
        query_timeout_seconds=10,
    )

    assert [field["name"] for field in collection.get_system_fields()] == ["id", "_created_at", "_updated_at"]
    assert [field["name"] for field in collection.get_specific_fields()] == ["file", "file_name"]
    assert [field["name"] for field in collection.get_business_fields()] == ["file", "file_name", "title"]
    assert [field["name"] for field in collection.get_row_writable_fields()] == ["file", "file_name", "title"]


def test_document_collection_presets_include_immutable_specific_fields():
    service = CollectionService(session=None)

    preset_fields = service._ensure_document_preset_fields(  # noqa: SLF001
        [
            {
                "name": "vendor",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": False,
                "description": "Vendor",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            }
        ]
    )

    field_map = {field["name"]: field for field in preset_fields}
    assert field_map["file"]["category"] == FieldCategory.SPECIFIC.value
    assert field_map["title"]["category"] == FieldCategory.SPECIFIC.value
    assert field_map["source"]["category"] == FieldCategory.SPECIFIC.value
    assert field_map["vendor"]["category"] == FieldCategory.USER.value


def test_document_collection_rejects_admin_defined_specific_fields():
    service = CollectionService(session=None)

    try:
        service._validate_admin_defined_fields(  # noqa: SLF001
            [
                {
                    "name": "title",
                    "category": FieldCategory.USER.value,
                    "data_type": FieldType.INTEGER.value,
                }
            ],
            CollectionType.DOCUMENT.value,
        )
    except InvalidSchemaError as exc:
        assert "reserved for document-specific immutable fields" in str(exc)
    else:
        raise AssertionError("Expected InvalidSchemaError for reserved document-specific field")


def test_schema_operation_contract_for_rename_and_alter():
    rename_op = SchemaOperation(op="rename", name="vendor", new_name="supplier")
    assert rename_op.op == "rename"
    assert rename_op.name == "vendor"
    assert rename_op.new_name == "supplier"

    alter_op = SchemaOperation(
        op="alter",
        name="title",
        field={
            "name": "title",
            "category": "user",
            "data_type": "text",
            "required": True,
            "description": "Title",
            "filterable": True,
            "sortable": True,
            "used_in_retrieval": True,
            "used_in_prompt_context": True,
        },
    )
    assert alter_op.field is not None
    assert alter_op.field.required is True


def test_update_collection_request_requires_actual_changes():
    request = UpdateCollectionRequest(
        name="New Name",
        schema_ops=[
            {
                "op": "add",
                "field": {
                    "name": "vendor",
                    "category": "user",
                    "data_type": "text",
                    "required": False,
                    "description": "Vendor",
                    "filterable": True,
                    "sortable": True,
                    "used_in_retrieval": True,
                    "used_in_prompt_context": True,
                },
            }
        ],
    )
    assert request.name == "New Name"
    assert len(request.schema_ops) == 1


async def test_table_collection_status_snapshot_created_and_ready():
    service = CollectionService(session=None)

    created_collection = _table_collection()
    created_snapshot = await service.get_status_snapshot(created_collection)
    assert created_snapshot["status"] == "created"
    assert created_snapshot["details"]["status_reason"] == "no_rows"
    assert created_snapshot["details"]["kind"] == "table"

    ready_collection = _table_collection()
    ready_collection.total_rows = 2
    ready_snapshot = await service.get_status_snapshot(ready_collection)
    assert ready_snapshot["status"] == "ready"
    assert ready_snapshot["details"]["status_reason"] == "rows_available_no_vector_required"


async def test_table_vector_collection_status_snapshot_ingesting_and_error():
    service = CollectionService(session=None)

    ingesting_collection = _table_collection()
    ingesting_collection.total_rows = 3
    ingesting_collection.vectorized_rows = 1
    ingesting_collection.failed_rows = 0
    ingesting_collection.qdrant_collection_name = "coll_test_tickets"
    ingesting_snapshot = await service.get_status_snapshot(ingesting_collection)
    assert ingesting_snapshot["status"] == "ingesting"
    assert ingesting_snapshot["details"]["status_reason"] == "vectorization_in_progress"

    error_collection = _table_collection()
    error_collection.total_rows = 2
    error_collection.vectorized_rows = 0
    error_collection.failed_rows = 2
    error_collection.qdrant_collection_name = "coll_test_tickets"
    error_snapshot = await service.get_status_snapshot(error_collection)
    assert error_snapshot["status"] == "error"
    assert error_snapshot["details"]["status_reason"] == "all_rows_vectorization_failed"


async def test_document_collection_status_snapshot_uses_document_lifecycle_reason():
    execute_result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(agg_status="ready", status="completed"),
            SimpleNamespace(agg_status="ready", status="completed"),
        ]
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    service = CollectionService(session=session)

    collection = Collection(
        id=uuid4(),
        data_instance_id=uuid4(),
        tenant_id=uuid4(),
        collection_type=CollectionType.DOCUMENT.value,
        slug="docs",
        name="Docs",
        description="Document collection",
        table_name="coll_test_docs",
        fields=[],
        status="created",
        total_rows=0,
        vectorized_rows=0,
        total_chunks=0,
        failed_rows=0,
        is_active=True,
        allow_unfiltered_search=False,
        max_limit=100,
        query_timeout_seconds=10,
    )

    snapshot = await service.get_status_snapshot(collection)

    assert snapshot["status"] == "ready"
    assert snapshot["details"]["kind"] == "document"
    assert snapshot["details"]["status_reason"] == "all_documents_ready"


def test_collection_doc_search_source_name_prefers_title_then_filename():
    tool = CollectionDocSearchTool()

    class Row:
        def __init__(self, id, name, title, filename):
            self.id = id
            self.name = name
            self.title = title
            self.filename = filename

    rows = [
        Row(uuid4(), None, "Document title", "doc.txt"),
        Row(uuid4(), None, None, "fallback.txt"),
    ]

    result = {
        str(rows[0].id): (rows[0].name or rows[0].title or rows[0].filename or "Без названия"),
        str(rows[1].id): (rows[1].name or rows[1].title or rows[1].filename or "Без названия"),
    }

    assert result[str(rows[0].id)] == "Document title"
    assert result[str(rows[1].id)] == "fallback.txt"


def test_collection_public_row_serialization_hides_operational_fields():
    collection = _table_collection()
    row = {
        "id": uuid4(),
        "title": "Incident 1",
        "priority": 2,
        "opened_at": None,
        "meta": {"owner": "ops"},
        "_created_at": "2026-03-22T10:00:00Z",
        "_updated_at": "2026-03-22T10:01:00Z",
        "_vector_status": "done",
        "_vector_chunk_count": 3,
        "_vector_error": None,
    }

    serialized = CollectionRowService._serialize_row(collection, row)

    assert serialized["id"] == row["id"]
    assert serialized["title"] == "Incident 1"
    assert serialized["priority"] == 2
    assert serialized["meta"] == {"owner": "ops"}
    assert "_created_at" not in serialized
    assert "_updated_at" not in serialized
    assert "_vector_status" not in serialized
    assert "_vector_chunk_count" not in serialized


def test_row_payload_validation_enforces_required_and_known_fields():
    service = CollectionService(session=None)
    collection = _table_collection()

    try:
        service._validate_and_prepare_row_payload(  # noqa: SLF001
            collection,
            {"priority": 1},
            partial=False,
        )
    except RowValidationError as exc:
        assert "Required field 'title' is missing" in str(exc)
    else:
        raise AssertionError("Expected RowValidationError for missing required field")

    try:
        service._validate_and_prepare_row_payload(  # noqa: SLF001
            collection,
            {"title": "ok", "unknown": "x"},
            partial=False,
        )
    except RowValidationError as exc:
        assert "Unknown fields: unknown" in str(exc)
    else:
        raise AssertionError("Expected RowValidationError for unknown field")


def test_row_payload_validation_coerces_supported_types():
    service = CollectionService(session=None)
    collection = Collection(
        id=uuid4(),
        data_instance_id=uuid4(),
        tenant_id=uuid4(),
        collection_type=CollectionType.TABLE.value,
        slug="typed_rows",
        name="Typed Rows",
        description="Schema with all main types",
        table_name="coll_test_typed_rows",
        fields=[
            {
                "name": "title",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": True,
                "description": "Title",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            },
            {
                "name": "count",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.INTEGER.value,
                "required": False,
                "description": "Count",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "ratio",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.FLOAT.value,
                "required": False,
                "description": "Ratio",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "enabled",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.BOOLEAN.value,
                "required": False,
                "description": "Enabled",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "opened_at",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.DATETIME.value,
                "required": False,
                "description": "Opened at",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "due_date",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.DATE.value,
                "required": False,
                "description": "Due date",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "meta",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.JSON.value,
                "required": False,
                "description": "Meta",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
        ],
        status="ready",
        total_rows=0,
        vectorized_rows=0,
        total_chunks=0,
        failed_rows=0,
        is_active=True,
        allow_unfiltered_search=False,
        max_limit=100,
        query_timeout_seconds=10,
    )

    prepared = service._validate_and_prepare_row_payload(  # noqa: SLF001
        collection,
        {
            "title": 42,
            "count": "12",
            "ratio": "1.25",
            "enabled": "true",
            "opened_at": "2026-03-22T12:34:56Z",
            "due_date": "2026-03-25",
            "meta": "{\"team\":\"ops\"}",
        },
        partial=False,
    )

    assert prepared["title"] == "42"
    assert prepared["count"] == 12
    assert prepared["ratio"] == 1.25
    assert prepared["enabled"] is True
    assert isinstance(prepared["opened_at"], datetime)
    assert isinstance(prepared["due_date"], date)
    assert prepared["meta"] == {"team": "ops"}
