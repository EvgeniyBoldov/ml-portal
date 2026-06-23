from __future__ import annotations

from typing import Iterable, Sequence

from app.agents.contracts import (
    PublishedCollectionSummary,
    PublishedOperationSummary,
    ResolvedDataInstance,
    ResolvedOperation,
)


def summarize_input_schema(schema: dict | None, *, max_items: int = 4) -> list[str]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = {
        str(item).strip()
        for item in (schema.get("required") or [])
        if str(item).strip()
    }
    summary: list[str] = []
    for key, value in properties.items():
        name = str(key).strip()
        if not name:
            continue
        if len(summary) >= max_items:
            break
        field_type = ""
        if isinstance(value, dict):
            raw_type = str(value.get("type") or "").strip()
            if raw_type:
                field_type = f": {raw_type}"
        suffix = " (required)" if name in required else ""
        summary.append(f"{name}{field_type}{suffix}")
    return summary


def build_published_operation_summary(
    operation: ResolvedOperation,
    *,
    collection: ResolvedDataInstance | None = None,
) -> PublishedOperationSummary:
    readiness = getattr(collection, "readiness", None)
    return PublishedOperationSummary(
        operation_slug=operation.operation_slug,
        canonical_name=operation.operation,
        scope_kind=operation.scope,
        domain=operation.published_domain,
        title=operation.name,
        description=operation.description,
        result_kind=operation.result_kind,
        collection_slug=operation.collection_slug or getattr(collection, "collection_slug", None),
        collection_type=getattr(collection, "collection_type", None),
        collection_purpose=getattr(collection, "usage_purpose", None),
        collection_readiness=str(getattr(readiness, "status", "") or "").strip() or None,
        schema_freshness=str(getattr(readiness, "schema_freshness", "") or "").strip() or None,
        provider_kind=operation.source,
        input_schema_summary=list(operation.input_schema_summary or summarize_input_schema(operation.input_schema)),
        side_effects=operation.side_effects,
        risk_level=operation.risk_level,
    )


def build_published_collection_summary(
    collection: ResolvedDataInstance,
    *,
    operations: Sequence[ResolvedOperation],
) -> PublishedCollectionSummary:
    readiness = getattr(collection, "readiness", None)
    collection_slug = str(collection.collection_slug or collection.slug).strip()
    op_slugs = [
        str(getattr(item, "operation_slug", "")).strip()
        for item in operations
        if str(getattr(item, "collection_slug", "")).strip() == collection_slug
        and str(getattr(item, "operation_slug", "")).strip()
    ]
    return PublishedCollectionSummary(
        collection_slug=collection_slug,
        collection_type=collection.collection_type,
        title=str(getattr(collection, "name", "") or "").strip() or None,
        purpose=collection.usage_purpose,
        data_description=collection.data_description or collection.description,
        readiness_status=str(getattr(readiness, "status", "") or "").strip() or None,
        schema_freshness=str(getattr(readiness, "schema_freshness", "") or "").strip() or None,
        missing_requirements=[
            str(item).strip()
            for item in (getattr(readiness, "missing_requirements", None) or [])
            if str(item).strip()
        ],
        available_operation_slugs=sorted(set(op_slugs)),
    )


def attach_published_operation_summaries(
    operations: Sequence[ResolvedOperation],
    collections: Sequence[ResolvedDataInstance],
) -> list[PublishedOperationSummary]:
    collection_map = {
        str(item.collection_slug or item.slug).strip(): item
        for item in collections
        if str(item.collection_slug or item.slug).strip()
    }
    summaries: list[PublishedOperationSummary] = []
    for operation in operations:
        collection = collection_map.get(str(operation.collection_slug or "").strip())
        summary = build_published_operation_summary(operation, collection=collection)
        operation.published = summary
        summaries.append(summary)
    return summaries


def build_published_collection_summaries(
    collections: Sequence[ResolvedDataInstance],
    operations: Sequence[ResolvedOperation],
) -> list[PublishedCollectionSummary]:
    return [
        build_published_collection_summary(item, operations=operations)
        for item in collections
        if str(item.collection_slug or item.slug).strip()
    ]


def serialize_published_operations(
    operations: Iterable[ResolvedOperation],
) -> list[dict]:
    payload: list[dict] = []
    for operation in operations:
        summary = operation.published or build_published_operation_summary(operation)
        payload.append(summary.model_dump(mode="json"))
    return payload


def serialize_published_collections(
    collections: Sequence[ResolvedDataInstance],
    operations: Sequence[ResolvedOperation],
) -> list[dict]:
    return [
        summary.model_dump(mode="json")
        for summary in build_published_collection_summaries(collections, operations)
    ]
