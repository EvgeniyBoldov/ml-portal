"""Semantic resolver for remote SQL collections (catalog-first placeholder)."""
from __future__ import annotations

from typing import List

from app.agents.collection_resolvers.base import (
    BaseCollectionTypeResolver,
    ResolvedCollection,
    field_hint,
    normalize_str_list,
)
from app.models.collection import Collection
from app.models.tool_instance import ToolInstance


class RemoteSqlCollectionResolver(BaseCollectionTypeResolver):
    collection_type = "sql"

    def build(self, instance: ToolInstance, collection: Collection) -> ResolvedCollection:
        semantic_profile, policy_hints, semantic_version = self.semantic_bundle(collection)
        summary = (
            str(semantic_profile.get("summary") or "").strip()
            or collection.description
            or f"Remote SQL catalog collection '{collection.name}' representing external tables and schemas."
        )
        use_cases = str(semantic_profile.get("use_cases") or "").strip() or (
            "Useful for schema discovery, selecting remote tables, and planning SQL joins."
        )
        entity_types = normalize_str_list(semantic_profile.get("entity_types")) or [
            "remote_table",
            "remote_schema_object",
        ]

        limitations: List[str] = [
            "SQL collection profile is catalog-oriented and currently treated as a minimal runtime placeholder.",
            "Use SQL operations to fetch live data and validate table relationships.",
            "Collection remains the source of truth for runtime binding metadata.",
        ]
        if collection.status != "ready":
            limitations.append(f"Current collection readiness is '{collection.status}'.")
        semantic_limitations = str(semantic_profile.get("limitations") or "").strip()
        if semantic_limitations:
            limitations.append(semantic_limitations)

        raw_examples = semantic_profile.get("examples")
        if raw_examples not in (None, "", [], {}):
            examples = raw_examples
        else:
            examples = [
                "найти таблицы по домену и подготовить join план",
                "проверить поля и ключи удаленной таблицы перед запросом",
            ]
        schema_hints = {
            "instance_domain": instance.domain,
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "collection_type": collection.collection_type,
            "retrieval_profile": "remote.sql.catalog",
            "rerank_mode": "none",
            "collection_status": collection.status,
            "semantic_version": semantic_version,
            "transport": self.transport_profile(instance),
            "table_name": collection.table_name,
            "table_schema": collection.table_schema or {},
            "last_sync_at": collection.last_sync_at.isoformat() if collection.last_sync_at else None,
            "user_fields": [field_hint(field) for field in collection.get_user_fields()],
            "specific_fields": [field_hint(field) for field in collection.get_specific_fields()],
            "system_fields": [field_hint(field) for field in collection.get_system_fields()],
            "filterable_fields": [field["name"] for field in collection.get_filterable_fields()],
            "sortable_fields": [field["name"] for field in collection.get_sortable_fields()],
            "prompt_context_fields": [field["name"] for field in collection.get_prompt_context_fields()],
            "retrieval_fields": list(collection.vector_fields),
            "semantic_profile": semantic_profile,
            "policy_hints": policy_hints,
        }
        return ResolvedCollection(
            id=self.profile_id(collection),
            summary=summary,
            entity_types=entity_types,
            use_cases=use_cases,
            limitations=" ".join(limitations),
            policy_hints=policy_hints,
            schema_hints=schema_hints,
            examples=examples,
            semantic_source=self.semantic_source(collection),
        )
