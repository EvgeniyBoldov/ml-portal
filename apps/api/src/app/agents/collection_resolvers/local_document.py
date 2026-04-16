"""Semantic resolver for local document collections."""
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


class LocalDocumentCollectionResolver(BaseCollectionTypeResolver):
    collection_type = "document"

    def build(self, instance: ToolInstance, collection: Collection) -> ResolvedCollection:
        semantic_profile, policy_hints, semantic_version = self.semantic_bundle(collection)

        summary = (
            str(semantic_profile.get("summary") or "").strip()
            or collection.description
            or f"Local document collection '{collection.name}' exposed as a runtime data instance."
        )
        use_cases = str(semantic_profile.get("use_cases") or "").strip() or (
            "Useful for semantic lookup across uploaded documents, excerpts, and collection metadata."
        )
        entity_types = normalize_str_list(semantic_profile.get("entity_types")) or ["document"]

        limitations: List[str] = [
            "Semantic meaning is derived from the linked collection schema.",
            "Collection remains the source of truth for field structure and readiness.",
            "Specific file fields are platform-managed and immutable.",
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
                "найти документ по регламенту или фразе из текста",
                "проверить источник и скачать исходный файл",
            ]
        schema_hints = {
            "instance_domain": instance.domain,
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "collection_type": collection.collection_type,
            "retrieval_profile": "document.semantic",
            "rerank_mode": "required",
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
