from __future__ import annotations

from typing import Iterable, Sequence

from app.agents.contracts import (
    PublishedCollectionSummary,
    PublishedOperationSummary,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.operation_publication import build_collection_workflow_steps
from app.agents.runtime.prompt_contract import build_prompt_input_schema, summarize_prompt_input_schema


def build_published_operation_summary(
    operation: ResolvedOperation,
    *,
    collection: ResolvedDataInstance | None = None,
) -> PublishedOperationSummary:
    readiness = getattr(collection, "readiness", None)
    return PublishedOperationSummary(
        operation_slug=str(getattr(operation, "operation_slug", "") or "").strip(),
        canonical_name=str(getattr(operation, "operation", "") or "").strip(),
        scope_kind=getattr(operation, "scope", "collection"),
        domain=getattr(operation, "published_domain", None),
        title=getattr(operation, "name", None),
        description=getattr(operation, "description", None),
        result_kind=getattr(operation, "result_kind", None),
        collection_slug=getattr(operation, "collection_slug", None) or getattr(collection, "collection_slug", None),
        collection_type=getattr(collection, "collection_type", None),
        collection_purpose=getattr(collection, "usage_purpose", None),
        collection_readiness=str(getattr(readiness, "status", "") or "").strip() or None,
        schema_freshness=str(getattr(readiness, "schema_freshness", "") or "").strip() or None,
        provider_kind=getattr(operation, "source", None),
        input_schema_summary=list(
            getattr(operation, "input_schema_summary", None)
            or summarize_prompt_input_schema(build_prompt_input_schema(operation))
        ),
        side_effects=bool(getattr(operation, "side_effects", False)),
        risk_level=getattr(operation, "risk_level", "safe"),
    )


def _resolve_operation_summary(
    operation: ResolvedOperation,
    *,
    collection: ResolvedDataInstance | None = None,
) -> PublishedOperationSummary:
    published = getattr(operation, "published", None)
    if isinstance(published, PublishedOperationSummary):
        return published
    if published is not None:
        readiness = getattr(collection, "readiness", None)
        return PublishedOperationSummary(
            operation_slug=str(
                getattr(published, "operation_slug", None)
                or getattr(operation, "operation_slug", "")
                or ""
            ).strip(),
            canonical_name=str(
                getattr(published, "canonical_name", None)
                or getattr(operation, "operation", "")
                or ""
            ).strip(),
            scope_kind=getattr(published, "scope_kind", None) or getattr(operation, "scope", "collection"),
            domain=getattr(published, "domain", None) or getattr(operation, "published_domain", None),
            title=getattr(published, "title", None) or getattr(operation, "name", None),
            description=getattr(published, "description", None) or getattr(operation, "description", None),
            result_kind=getattr(published, "result_kind", None) or getattr(operation, "result_kind", None),
            collection_slug=getattr(published, "collection_slug", None)
            or getattr(operation, "collection_slug", None)
            or getattr(collection, "collection_slug", None),
            collection_type=getattr(published, "collection_type", None) or getattr(collection, "collection_type", None),
            collection_purpose=getattr(published, "collection_purpose", None) or getattr(collection, "usage_purpose", None),
            collection_readiness=str(getattr(readiness, "status", "") or "").strip() or None,
            schema_freshness=str(getattr(readiness, "schema_freshness", "") or "").strip() or None,
            provider_kind=getattr(published, "provider_kind", None) or getattr(operation, "source", None),
            input_schema_summary=list(
                getattr(published, "input_schema_summary", None)
                or getattr(operation, "input_schema_summary", None)
                or summarize_prompt_input_schema(build_prompt_input_schema(operation))
            ),
            side_effects=bool(getattr(published, "side_effects", getattr(operation, "side_effects", False))),
            risk_level=getattr(published, "risk_level", getattr(operation, "risk_level", "safe")),
        )
    return build_published_operation_summary(operation, collection=collection)


def build_published_collection_summary(
    collection: ResolvedDataInstance,
    *,
    operations: Sequence[ResolvedOperation],
) -> PublishedCollectionSummary:
    readiness = getattr(collection, "readiness", None)
    collection_slug = str(collection.collection_slug or collection.slug).strip()
    collection_operations = [
        item
        for item in operations
        if str(getattr(item, "collection_slug", "")).strip() == collection_slug
    ]
    operation_summaries = [
        _resolve_operation_summary(item, collection=collection)
        for item in collection_operations
    ]
    op_slugs = [
        str(getattr(item, "operation_slug", "")).strip()
        for item in operation_summaries
        if str(getattr(item, "operation_slug", "")).strip()
    ]
    collection_type = getattr(collection, "collection_type", None)
    return PublishedCollectionSummary(
        collection_slug=collection_slug,
        collection_type=collection_type,
        title=str(getattr(collection, "name", "") or "").strip() or None,
        purpose=collection.usage_purpose,
        data_description=collection.data_description,
        usage_rules=getattr(collection, "usage_rules", None),
        readiness_status=str(getattr(readiness, "status", "") or "").strip() or None,
        schema_freshness=str(getattr(readiness, "schema_freshness", "") or "").strip() or None,
        missing_requirements=[
            str(item).strip()
            for item in (getattr(readiness, "missing_requirements", None) or [])
            if str(item).strip()
        ],
        available_operation_slugs=sorted(set(op_slugs)),
        available_operations=operation_summaries,
        recommended_flow=build_collection_workflow_steps(
            collection_type=str(collection_type or "").strip().lower(),
            canonical_operations=[
                str(getattr(item, "canonical_name", "")).strip()
                for item in operation_summaries
            ],
        ),
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
        summary = _resolve_operation_summary(operation, collection=collection)
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
        summary = _resolve_operation_summary(operation)
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
