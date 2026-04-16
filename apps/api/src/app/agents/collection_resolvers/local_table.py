"""Semantic resolver for local table collections."""
from __future__ import annotations

from typing import List

from app.agents.collection_resolvers.base import (
    BaseCollectionTypeResolver,
    ResolvedCollection,
    field_hint,
    normalize_str_list,
)
from app.models.tool_instance import ToolInstance
from app.models.collection import Collection


class LocalTableCollectionResolver(BaseCollectionTypeResolver):
    collection_type = "table"

    def build(self, instance: ToolInstance, collection: Collection) -> ResolvedCollection:
        semantic_profile, policy_hints, semantic_version = self.semantic_bundle(collection)

        summary = (
            str(semantic_profile.get("summary") or "").strip()
            or collection.description
            or f"Local table collection '{collection.name}' exposed as a runtime data instance."
        )
        use_cases = str(semantic_profile.get("use_cases") or "").strip() or (
            "Useful for structured search, filtering, and aggregation over collection rows."
        )
        entity_types = normalize_str_list(semantic_profile.get("entity_types")) or ["record"]

        limitations: List[str] = [
            "Semantic meaning is derived from the linked collection schema.",
            "Collection remains the source of truth for field structure and readiness.",
            "Only user fields participate in writable business schema.",
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
            examples = {
                "field_counts": {
                    "system": len(collection.get_system_fields()),
                    "specific": len(collection.get_specific_fields()),
                    "user": len(collection.get_user_fields()),
                },
                "suggested_tasks": [
                    "найти строки по фильтру",
                    "посчитать агрегаты и проверить конкретную запись",
                ],
            }
        schema_hints = {
            "instance_domain": instance.domain,
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "collection_type": collection.collection_type,
            "retrieval_profile": "table.hybrid",
            "rerank_mode": "optional",
            "collection_status": collection.status,
            "semantic_version": semantic_version,
            "transport": self.transport_profile(instance),
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
