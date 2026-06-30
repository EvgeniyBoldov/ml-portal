from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text

from app.agents.contracts import ResolvedDataInstance, ResolvedOperation
from app.agents.operation_publication import build_collection_workflow_steps
from app.agents.runtime.published_capabilities import build_published_operation_summary
from app.models.collection import Collection, CollectionType, FieldType

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOCAL_ENRICHMENT_COLLECTION_TYPES = {
    CollectionType.TABLE.value,
    CollectionType.DOCUMENT.value,
    CollectionType.TEMPLATE.value,
}
_EXACT_DISTINCT_LIMIT = 25
_TOP_VALUES_LIMIT = 10


@dataclass(slots=True)
class CollectionInfoMetadataLoader:
    def build_collection_payload(self, collection: Collection) -> Dict[str, Any]:
        current_version = getattr(collection, "current_version", None)
        return {
            "id": str(collection.id),
            "slug": collection.slug,
            "name": collection.name,
            "type": collection.collection_type,
            "status": collection.status,
            "description": getattr(current_version, "data_description", None),
            "usage_purpose": getattr(current_version, "usage_purpose", None),
            "usage_rules": getattr(current_version, "usage_rules", None),
            "table_name": collection.table_name,
        }

    def build_readiness_payload(
        self,
        *,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> Dict[str, Any]:
        provider_healths = sorted(
            {
                str(getattr(item.target, "health_status", "") or "").strip()
                for item in operations
                if getattr(item, "target", None) is not None
                and str(getattr(item.target, "health_status", "") or "").strip()
            }
        )
        all_have_credentials = all(
            bool(getattr(item.target, "has_credentials", False))
            for item in operations
            if getattr(item, "source", None) == "mcp"
        )
        if operations:
            status = "ready"
        else:
            status = "no_operations"
        return {
            "status": status,
            "schema_freshness": getattr(collection, "schema_status", None),
            "provider_health": provider_healths,
            "credential_status": (
                "available"
                if all_have_credentials or not any(getattr(item, "source", None) == "mcp" for item in operations)
                else "missing"
            ),
            "operations_count": len(operations),
            "last_sync_at": collection.last_sync_at.isoformat() if collection.last_sync_at else None,
        }

    def build_resolved_data_instance(self, collection: Collection) -> ResolvedDataInstance:
        current_version = getattr(collection, "current_version", None)
        return ResolvedDataInstance(
            instance_id=str(collection.id),
            slug=collection.slug,
            name=collection.name,
            domain=f"collection.{collection.collection_type}",
            collection_id=str(collection.id),
            collection_slug=collection.slug,
            placement="local" if collection.is_local else "remote",
            description=getattr(current_version, "data_description", None),
            entity_type=collection.entity_type or None,
            collection_type=collection.collection_type,
            data_description=getattr(current_version, "data_description", None),
            usage_purpose=getattr(current_version, "usage_purpose", None),
            usage_rules=getattr(current_version, "usage_rules", None),
            remote_tables=[],
            readiness=None,
        )


@dataclass(slots=True)
class CollectionInfoOperationResolver:
    def resolve_for_collection(
        self,
        *,
        runtime_deps: Any,
        collection_slug: str,
        collection: Collection,
    ) -> List[ResolvedOperation]:
        resolved_operations = getattr(runtime_deps, "resolved_operations", None)
        if isinstance(resolved_operations, list) and resolved_operations:
            return [
                operation
                for operation in resolved_operations
                if str(getattr(operation, "collection_slug", "") or "").strip() == collection_slug
            ]

        graph_raw = getattr(runtime_deps, "execution_graph", None)
        bindings = getattr(graph_raw, "bindings", {}) if graph_raw is not None else {}
        operations: List[ResolvedOperation] = []
        for operation_slug, binding in dict(bindings or {}).items():
            context = getattr(binding, "context", None)
            if context is None or str(getattr(context, "collection_slug", "") or "").strip() != collection_slug:
                continue
            target = getattr(binding, "target", None)
            if target is None:
                continue
            operations.append(
                ResolvedOperation(
                    operation_slug=operation_slug,
                    operation=self._canonical_name_from_slug(operation_slug),
                    name=self._title_from_slug(operation_slug),
                    scope="collection",
                    description="",
                    input_schema={},
                    output_schema=None,
                    data_instance_id=str(getattr(context, "collection_id", None) or getattr(collection, "id", "")),
                    data_instance_slug=collection_slug,
                    collection_slug=collection_slug,
                    provider_instance_id=getattr(target, "provider_instance_id", None),
                    provider_instance_slug=getattr(target, "provider_instance_slug", None),
                    source=getattr(target, "provider_type", "local"),
                    target=target,
                )
            )
        return operations

    @staticmethod
    def _canonical_name_from_slug(operation_slug: str) -> str:
        normalized = str(operation_slug or "").strip()
        if normalized.startswith("instance."):
            parts = normalized.split(".", 2)
            if len(parts) == 3:
                return parts[2]
        return normalized

    @staticmethod
    def _title_from_slug(operation_slug: str) -> str:
        canonical = CollectionInfoOperationResolver._canonical_name_from_slug(operation_slug)
        leaf = canonical.split(".")[-1].replace("_", " ").strip()
        return leaf.title() if leaf else canonical

    def build_operations_payload(
        self,
        *,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> List[Dict[str, Any]]:
        resolved_collection = CollectionInfoMetadataLoader().build_resolved_data_instance(collection)
        payload: List[Dict[str, Any]] = []
        for operation in operations:
            published = getattr(operation, "published", None)
            if published is None:
                summary = build_published_operation_summary(operation, collection=resolved_collection)
            else:
                summary = published
            payload.append(
                {
                    "operation_slug": summary.operation_slug,
                    "canonical_name": summary.canonical_name,
                    "title": summary.title,
                    "description": summary.description,
                    "result_kind": summary.result_kind,
                    "input_schema_summary": list(summary.input_schema_summary or []),
                    "risk_level": summary.risk_level,
                    "side_effects": bool(summary.side_effects),
                }
            )
        payload.sort(key=lambda item: str(item.get("canonical_name") or item.get("operation_slug") or ""))
        return payload

    def build_contracts_payload(
        self,
        *,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> Dict[str, Any]:
        canonical_names = [
            self._canonical_name_from_slug(item.operation_slug)
            for item in operations
        ]
        current_version = getattr(collection, "current_version", None)
        return {
            "usage_rules": getattr(current_version, "usage_rules", None),
            "workflow": build_collection_workflow_steps(
                collection_type=str(collection.collection_type or "").strip().lower(),
                canonical_operations=canonical_names,
            ),
            "identifier_rules": self._identifier_rules(canonical_names),
        }

    @staticmethod
    def _identifier_rules(canonical_names: Iterable[str]) -> List[str]:
        names = set(canonical_names)
        rules: List[str] = []
        if "collection.document.get" in names:
            rules.append("Use document_id only from collection.document.search or collection.document.list results.")
        if "collection.template.get_schema" in names or "collection.template.fill" in names:
            rules.append("Use row_id only from collection.template.list or collection.template.search results.")
        if "collection.info" in names:
            rules.append("Call collection.info first when fields, filters, values, or operation sequence are unclear.")
        return rules


@dataclass(slots=True)
class LocalCollectionInfoEnricher:
    async def build(
        self,
        *,
        session: Any,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> Dict[str, Any]:
        table_name = str(getattr(collection, "table_name", "") or "").strip()
        if not table_name or not _is_safe_identifier(table_name):
            return {
                "status": "unavailable",
                "type": str(collection.collection_type or "").strip(),
                "message": "Local runtime enrichment requires a valid local table.",
                "data": {},
                "available_operation_count": len(operations),
            }

        row_count = await _scalar_count(session, f"SELECT COUNT(*)::bigint FROM {table_name}")
        field_profiles: Dict[str, Any] = {}
        for field in _iter_profiled_fields(collection):
            field_name = str(field.get("name") or "").strip()
            if not field_name or not _is_safe_identifier(field_name):
                continue
            profile = await self._build_field_profile(
                session=session,
                table_name=table_name,
                field=field,
            )
            if profile is not None:
                field_profiles[field_name] = profile

        temporal_bounds = await self._build_temporal_bounds(session=session, table_name=table_name)
        return {
            "status": "ready",
            "type": str(collection.collection_type or "").strip(),
            "data": {
                "row_count": row_count,
                "field_profiles": field_profiles,
                "temporal_bounds": temporal_bounds,
            },
            "available_operation_count": len(operations),
        }

    async def _build_field_profile(
        self,
        *,
        session: Any,
        table_name: str,
        field: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        field_name = str(field.get("name") or "").strip()
        data_type = str(field.get("data_type") or "").strip()
        null_count = await _scalar_count(
            session,
            f"SELECT COUNT(*)::bigint FROM {table_name} WHERE {field_name} IS NULL",
        )
        profile: Dict[str, Any] = {
            "data_type": data_type,
            "null_count": null_count,
        }

        if data_type in {FieldType.DATE.value, FieldType.DATETIME.value}:
            bounds = await _min_max(session, table_name=table_name, field_name=field_name)
            profile.update(bounds)
            profile["complete"] = True
            return profile

        if data_type in {FieldType.INTEGER.value, FieldType.FLOAT.value}:
            distinct_count = await _distinct_count(session, table_name=table_name, field_name=field_name)
            values_payload = await _build_values_payload(
                session=session,
                table_name=table_name,
                field_name=field_name,
                distinct_count=distinct_count,
            )
            bounds = await _min_max(session, table_name=table_name, field_name=field_name)
            profile.update(bounds)
            profile["distinct_count"] = distinct_count
            profile.update(values_payload)
            return profile

        distinct_count = await _distinct_count(session, table_name=table_name, field_name=field_name)
        values_payload = await _build_values_payload(
            session=session,
            table_name=table_name,
            field_name=field_name,
            distinct_count=distinct_count,
        )
        profile["distinct_count"] = distinct_count
        profile.update(values_payload)
        return profile

    async def _build_temporal_bounds(self, *, session: Any, table_name: str) -> Dict[str, Any]:
        row = (
            await session.execute(
                text(
                    f"SELECT "
                    f"MIN(_created_at) AS first_created_at, "
                    f"MAX(_created_at) AS last_created_at, "
                    f"MIN(_updated_at) AS first_updated_at, "
                    f"MAX(_updated_at) AS last_updated_at "
                    f"FROM {table_name}"
                )
            )
        ).mappings().first() or {}
        return {
            "first_created_at": _isoformat_or_none(row.get("first_created_at")),
            "last_created_at": _isoformat_or_none(row.get("last_created_at")),
            "first_updated_at": _isoformat_or_none(row.get("first_updated_at")),
            "last_updated_at": _isoformat_or_none(row.get("last_updated_at")),
        }


@dataclass(slots=True)
class RemoteCollectionInfoEnricher:
    async def build(
        self,
        *,
        session: Any,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> Dict[str, Any]:
        _ = session
        return {
            "status": "stub",
            "type": str(collection.collection_type or "").strip(),
            "message": "Remote runtime enrichment is not implemented yet for this collection type.",
            "data": {},
            "available_operation_count": len(operations),
        }


@dataclass(slots=True)
class CollectionInfoEnrichmentProvider:
    local_enricher: LocalCollectionInfoEnricher
    remote_enricher: RemoteCollectionInfoEnricher

    async def build_runtime_enrichment(
        self,
        *,
        session: Any,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
    ) -> Dict[str, Any]:
        collection_type = str(collection.collection_type or "").strip().lower()
        if collection_type in _LOCAL_ENRICHMENT_COLLECTION_TYPES:
            return await self.local_enricher.build(
                session=session,
                collection=collection,
                operations=operations,
            )
        return await self.remote_enricher.build(
            session=session,
            collection=collection,
            operations=operations,
        )


@dataclass(slots=True)
class CollectionInfoResponseBuilder:
    metadata_loader: CollectionInfoMetadataLoader
    operation_resolver: CollectionInfoOperationResolver
    enrichment_provider: CollectionInfoEnrichmentProvider

    async def build(
        self,
        *,
        session: Any,
        collection: Collection,
        operations: Sequence[ResolvedOperation],
        legacy_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        collection_payload = self.metadata_loader.build_collection_payload(collection)
        return {
            "collection": collection_payload,
            "readiness": self.metadata_loader.build_readiness_payload(collection=collection, operations=operations),
            "operations": self.operation_resolver.build_operations_payload(collection=collection, operations=operations),
            "contracts": self.operation_resolver.build_contracts_payload(collection=collection, operations=operations),
            "schema": legacy_payload.get("schema") or {},
            "runtime_enrichment": await self.enrichment_provider.build_runtime_enrichment(
                session=session,
                collection=collection,
                operations=operations,
            ),
            "legacy": {
                "filter_hints": legacy_payload.get("filter_hints") or {},
                "stats": legacy_payload.get("stats") or {},
                "dimensions": legacy_payload.get("dimensions") or {},
                "remote_catalog": legacy_payload.get("remote_catalog") or {},
            },
            # Transitional top-level compatibility keys.
            "filter_hints": legacy_payload.get("filter_hints") or {},
            "stats": legacy_payload.get("stats") or {},
            "dimensions": legacy_payload.get("dimensions") or {},
            "remote_catalog": legacy_payload.get("remote_catalog") or {},
        }


def build_default_collection_info_response_builder() -> CollectionInfoResponseBuilder:
    return CollectionInfoResponseBuilder(
        metadata_loader=CollectionInfoMetadataLoader(),
        operation_resolver=CollectionInfoOperationResolver(),
        enrichment_provider=CollectionInfoEnrichmentProvider(
            local_enricher=LocalCollectionInfoEnricher(),
            remote_enricher=RemoteCollectionInfoEnricher(),
        ),
    )


def _is_safe_identifier(value: str) -> bool:
    return bool(value and _IDENTIFIER_PATTERN.match(value))


def _iter_profiled_fields(collection: Collection) -> List[Dict[str, Any]]:
    vector_fields = set(getattr(collection, "vector_fields", []) or [])
    fields: List[Dict[str, Any]] = []
    for field in collection.get_business_fields():
        field_name = str(field.get("name") or "").strip()
        data_type = str(field.get("data_type") or "").strip()
        if not field_name:
            continue
        if field_name in vector_fields:
            continue
        if data_type in {FieldType.FILE.value, FieldType.JSON.value}:
            continue
        fields.append(field)
    return fields


async def _scalar_count(session: Any, query: str) -> int:
    row = (await session.execute(text(query))).mappings().first() or {}
    value = next(iter(row.values()), 0)
    return int(value or 0)


async def _distinct_count(session: Any, *, table_name: str, field_name: str) -> int:
    row = (
        await session.execute(
            text(
                f"SELECT COUNT(DISTINCT {field_name})::bigint AS distinct_count "
                f"FROM {table_name} WHERE {field_name} IS NOT NULL"
            )
        )
    ).mappings().first() or {}
    return int(row.get("distinct_count") or 0)


async def _top_values(session: Any, *, table_name: str, field_name: str, limit: int) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                f"SELECT {field_name} AS value, COUNT(*)::bigint AS hits "
                f"FROM {table_name} "
                f"WHERE {field_name} IS NOT NULL "
                f"GROUP BY {field_name} "
                f"ORDER BY hits DESC, value ASC "
                f"LIMIT :limit"
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return [{"value": row.get("value"), "hits": int(row.get("hits") or 0)} for row in rows]


async def _min_max(session: Any, *, table_name: str, field_name: str) -> Dict[str, Any]:
    row = (
        await session.execute(
            text(
                f"SELECT MIN({field_name}) AS min_value, MAX({field_name}) AS max_value "
                f"FROM {table_name} WHERE {field_name} IS NOT NULL"
            )
        )
    ).mappings().first() or {}
    return {
        "min": _normalize_scalar(row.get("min_value")),
        "max": _normalize_scalar(row.get("max_value")),
    }


async def _build_values_payload(
    *,
    session: Any,
    table_name: str,
    field_name: str,
    distinct_count: int,
) -> Dict[str, Any]:
    if distinct_count <= _EXACT_DISTINCT_LIMIT:
        values = await _top_values(
            session,
            table_name=table_name,
            field_name=field_name,
            limit=_EXACT_DISTINCT_LIMIT,
        )
        return {
            "complete": True,
            "values": values,
        }
    top_values = await _top_values(
        session,
        table_name=table_name,
        field_name=field_name,
        limit=_TOP_VALUES_LIMIT,
    )
    return {
        "complete": False,
        "truncated": True,
        "top_values": top_values,
    }


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    return _isoformat_or_none(value) if hasattr(value, "isoformat") else value


def _isoformat_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
