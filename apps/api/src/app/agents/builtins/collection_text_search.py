"""
Collection Text Search Tool — векторный поиск по коллекциям с retrieval-enabled text fields.

Ищет в Qdrant-коллекции, привязанной к конкретной collection-коллекции
(collection.qdrant_collection_name). Возвращает найденные строки
с полными данными из SQL-таблицы.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Dict, List, Optional

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "Slug of the collection to search in",
        },
        "query": {
            "type": "string",
            "description": "Natural language search query for semantic similarity",
        },
        "field_name": {
            "type": "string",
            "description": (
                "Optional: specific vector-enabled field to search in. "
                "If not provided, searches across all vector fields."
            ),
        },
        "limit": {
            "type": "integer",
            "description": "Number of results to return (default: 10, max: 50)",
            "default": 10,
            "minimum": 1,
            "maximum": 50,
        },
        "filters": {
            "type": "object",
            "description": (
                "Optional SQL-level filters on row data. "
                "Keys are field names, values are exact-match values."
            ),
        },
    },
    "required": ["collection_slug", "query"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "hits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string"},
                    "score": {"type": "number"},
                    "matched_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "matched_fragments": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "primary_field": {"type": "string"},
                    "primary_fragment": {"type": "string"},
                    "row_data": {"type": "object"},
                },
            },
        },
        "total": {"type": "integer"},
        "collection": {"type": "string"},
        "vector_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


@register_tool
class CollectionTextSearchTool(VersionedTool):
    """
    Векторный (семантический) поиск по коллекциям с retrieval-enabled text fields.

    Такие коллекции могут иметь text-поля с `used_in_retrieval=true`.
    Эти поля векторизуются и хранятся в отдельной Qdrant-коллекции.

    Результаты обогащаются полными данными из SQL-таблицы.
    """

    tool_slug: ClassVar[str] = "collection.template.search"
    domains: ClassVar[list] = ["collection.template"]
    name: ClassVar[str] = "Template Search"
    description: ClassVar[str] = (
        "Semantic search within a template collection that has retrieval-enabled text fields. "
        "Use it to find the right template row by meaning before calling collection.template.get_schema "
        "or collection.template.fill. Returns matched text, relevance score, and full row data."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Vector search in collections with Qdrant + SQL row enrichment",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.agents.runtime.rerank_client import (
            RerankClientError,
            apply_rerank_to_items,
            rerank_scores,
        )
        from app.adapters.embeddings import EmbeddingServiceFactory
        from app.adapters.impl.qdrant import QdrantVectorStore
        from app.core.db import get_session_factory
        from app.services.collection.vector_lifecycle import (
            CollectionVectorLifecycleService,
            build_model_scoped_qdrant_collections,
        )
        from app.services.collection_service import CollectionService

        log = ctx.tool_logger("collection.template.search")

        collection_slug = args["collection_slug"]
        query = args["query"]
        field_name = args.get("field_name")
        try:
            limit = min(int(args.get("limit", 10)), 50)
        except (TypeError, ValueError):
            limit = 10
        payload_filters = args.get("filters", {})

        log.info(
            "Starting text collection search",
            collection=collection_slug,
            query=query[:100],
            field=field_name,
            limit=limit,
        )

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                # 1. Resolve collection
                service = CollectionService(session)
                collection = await service.get_by_slug(collection_slug)
                if not collection:
                    log.error("Collection not found", collection=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
                    )
                if collection_slug and str(collection.slug) != collection_slug:
                    log.error(
                        "Collection slug mismatch",
                        expected=collection_slug,
                        actual=collection.slug,
                    )
                    return ToolResult.fail(
                        f"Collection slug mismatch: expected '{collection_slug}', got '{collection.slug}'",
                        logs=log.entries_dict(),
                    )
                log.info(
                    "Resolved collection",
                    slug=collection.slug,
                    qdrant_collection_name=collection.qdrant_collection_name,
                    collection_type=collection.collection_type,
                )

                if not collection.has_vector_search:
                    log.error("Collection has no vector search", slug=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' does not have vector search enabled. "
                        f"Mark at least one text field with used_in_retrieval=true to enable it.",
                        logs=log.entries_dict(),
                    )

                if not collection.qdrant_collection_name:
                    log.error("No Qdrant collection name", slug=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' has no Qdrant collection configured.",
                        logs=log.entries_dict(),
                    )

                vector_fields = collection.vector_fields
                if field_name and field_name not in vector_fields:
                    log.error("Field not vector-enabled", field=field_name)
                    return ToolResult.fail(
                        f"Field '{field_name}' is not vector-enabled. "
                        f"Available vector fields: {', '.join(vector_fields)}",
                        logs=log.entries_dict(),
                    )

                # 2. Resolve effective embedding target models and search across all model-scoped collections
                vector_store = QdrantVectorStore()
                vector_lifecycle = CollectionVectorLifecycleService(session)
                target_models = await vector_lifecycle.resolve_target_vector_models(collection.tenant_id)
                if not target_models:
                    log.error("No embedding models")
                    return ToolResult.fail(
                        "Cannot determine embedding model for this collection.",
                        logs=log.entries_dict(),
                    )

                # 3. Build Qdrant filter
                qdrant_filter_must: List[tuple] = []
                if field_name:
                    qdrant_filter_must.append(("field_name", field_name))
                if payload_filters:
                    for fkey, fval in payload_filters.items():
                        qdrant_filter_must.append((fkey, fval))

                search_filter = {"must": qdrant_filter_must} if qdrant_filter_must else None

                # 4. Search across all model-scoped Qdrant collections
                results: list[dict[str, Any]] = []
                existing_collections = 0
                for model_alias, scoped_collection_name in build_model_scoped_qdrant_collections(
                    collection.qdrant_collection_name,
                    target_models,
                ):
                    exists = await vector_store.collection_exists(scoped_collection_name)
                    if not exists:
                        continue
                    existing_collections += 1
                    await EmbeddingServiceFactory.ensure_model_registered_async(session, model_alias)
                    embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                    query_embedding = await asyncio.to_thread(embedding_service.embed_texts, [query])
                    model_results = await vector_store.search(
                        collection=scoped_collection_name,
                        query=query_embedding[0],
                        top_k=limit * 2,
                        filter=search_filter,
                    )
                    for hit in model_results:
                        payload = hit.setdefault("payload", {})
                        payload.setdefault("embed_model_alias", model_alias)
                        payload.setdefault("qdrant_collection_name", scoped_collection_name)
                    results.extend(model_results)

                if existing_collections == 0:
                    log.warning("Qdrant collection does not exist yet")
                    fallback_hits = await self._fallback_keyword_hits(
                        session=session,
                        collection=collection,
                        query=query,
                        limit=limit,
                        vector_fields=vector_fields,
                    )
                    return ToolResult.ok(
                        data={
                            "hits": fallback_hits,
                            "total": len(fallback_hits),
                            "collection": collection.slug,
                            "vector_fields": vector_fields,
                        },
                        message=(
                            "Collection exists but has not been vectorized yet. "
                            "Returned fallback lexical matches."
                            if fallback_hits
                            else "Collection exists but has not been vectorized yet."
                        ),
                        logs=log.entries_dict(),
                    )

                if not results:
                    log.info("No results found")
                    fallback_hits = await self._fallback_keyword_hits(
                        session=session,
                        collection=collection,
                        query=query,
                        limit=limit,
                        vector_fields=vector_fields,
                    )
                    return ToolResult.ok(
                        data={
                            "hits": fallback_hits,
                            "total": len(fallback_hits),
                            "collection": collection.slug,
                            "vector_fields": vector_fields,
                        },
                        message=(
                            "No vector hits; returned fallback lexical matches."
                            if fallback_hits
                            else None
                        ),
                        logs=log.entries_dict(),
                    )

                # 5. Group by row_id, keep record-level summary
                rows_map: Dict[str, Dict[str, Any]] = {}
                for hit in results:
                    payload = hit.get("payload", {})
                    row_id = payload.get("row_id")
                    if not row_id:
                        continue
                    field = str(payload.get("field_name") or "").strip()
                    fragment = str(payload.get("text") or "").strip()
                    entry = rows_map.setdefault(
                        row_id,
                        {
                            "row_id": row_id,
                            "score": float(hit["score"]),
                            "primary_field": field,
                            "primary_fragment": fragment,
                            "matched_fields": set(),
                            "matched_fragments": [],
                        },
                    )
                    if hit["score"] > entry["score"]:
                        entry["score"] = float(hit["score"])
                        entry["primary_field"] = field
                        entry["primary_fragment"] = fragment
                    if field:
                        entry["matched_fields"].add(field)
                    if fragment:
                        entry["matched_fragments"].append(fragment)

                sorted_rows = sorted(
                    rows_map.values(), key=lambda r: r["score"], reverse=True
                )[:limit]

                # 5.1 Optional rerank for table collections (fallback to vector order on failure)
                if sorted_rows:
                    rerank_inputs = []
                    for row in sorted_rows:
                        primary_fragment = str(row.get("primary_fragment") or "").strip()
                        if primary_fragment:
                            rerank_inputs.append(primary_fragment)
                            continue
                        matched_fragments = row.get("matched_fragments") or []
                        rerank_inputs.append(str(matched_fragments[0]) if matched_fragments else "")
                    try:
                        reranked = await rerank_scores(
                            session=session,
                            query=query,
                            documents=rerank_inputs,
                            top_k=len(rerank_inputs),
                        )
                        sorted_rows = apply_rerank_to_items(sorted_rows, reranked, score_field="score")
                    except RerankClientError as exc:
                        log.warning("Rerank unavailable, keeping vector order", error=str(exc))

                # 6. Enrich with full row data from SQL
                row_ids = [r["row_id"] for r in sorted_rows]
                full_rows = await self._fetch_full_rows(session, collection, row_ids)

                # 7. Format output
                hits = []
                for row in sorted_rows:
                    row_data = full_rows.get(row["row_id"])
                    if not row_data:
                        continue

                    primary_fragment = row["primary_fragment"].strip()
                    if len(primary_fragment) > 500:
                        primary_fragment = primary_fragment[:497] + "..."

                    fragments: List[str] = []
                    for fragment in row.get("matched_fragments", []):
                        norm = fragment.strip()
                        if not norm:
                            continue
                        if len(norm) > 220:
                            norm = norm[:217] + "..."
                        if norm not in fragments:
                            fragments.append(norm)
                        if len(fragments) >= 3:
                            break

                    hit_entry: Dict[str, Any] = {
                        "row_id": row["row_id"],
                        "score": round(row["score"], 3),
                        "matched_fields": sorted(row.get("matched_fields", set())),
                        "matched_fragments": fragments,
                        "primary_field": row.get("primary_field", ""),
                        "primary_fragment": primary_fragment,
                        "row_data": row_data,
                    }

                    hits.append(hit_entry)

                log.info(
                    "Search completed",
                    hits_count=len(hits),
                    top_score=round(sorted_rows[0]["score"], 3) if sorted_rows else 0,
                )

                return ToolResult.ok(
                    data={
                        "hits": hits,
                        "total": len(hits),
                        "collection": collection.slug,
                        "vector_fields": vector_fields,
                    },
                    logs=log.entries_dict(),
                )

        except Exception as e:
            logger.error(f"Collection text search failed: {e}", exc_info=True)
            log.error("Search failed", error=str(e))
            return ToolResult.fail(f"Search failed: {str(e)}", logs=log.entries_dict())

    async def _fallback_keyword_hits(
        self,
        *,
        session: Any,
        collection: Any,
        query: str,
        limit: int,
        vector_fields: List[str],
    ) -> List[Dict[str, Any]]:
        from app.services.collection.row_service import CollectionRowService

        row_service = CollectionRowService(session)
        rows = await row_service.search(
            collection,
            limit=max(limit * 10, 50),
            offset=0,
            query=None,
        )

        preferred_fields = [
            field_name
            for field_name in (
                "title",
                "description",
                "semantic_description",
                *vector_fields,
            )
            if isinstance(field_name, str) and field_name.strip()
        ]
        query_text = query.strip().lower()
        query_tokens = {
            token
            for token in _TOKEN_RE.findall(query_text)
            if token
        }
        if not query_text or not query_tokens:
            return []

        scored_rows: List[Dict[str, Any]] = []
        for row in rows:
            best_field = ""
            best_fragment = ""
            best_score = 0.0

            for field_name in preferred_fields:
                raw_value = row.get(field_name)
                if not isinstance(raw_value, str):
                    continue
                value = raw_value.strip()
                if not value:
                    continue
                normalized = value.lower()
                field_tokens = {
                    token
                    for token in _TOKEN_RE.findall(normalized)
                    if token
                }
                overlap = len(query_tokens & field_tokens)
                if overlap == 0 and query_text not in normalized:
                    continue

                score = 0.0
                if query_text in normalized:
                    score += 5.0
                score += overlap / max(len(query_tokens), 1)
                if field_name == "title":
                    score += 1.5
                elif field_name == "description":
                    score += 1.0
                elif field_name == "semantic_description":
                    score += 0.8

                if score > best_score:
                    best_score = score
                    best_field = field_name
                    best_fragment = value[:500]

            if best_score <= 0:
                continue

            scored_rows.append(
                {
                    "row_id": str(row.get("id") or ""),
                    "score": round(best_score, 3),
                    "matched_fields": [best_field] if best_field else [],
                    "matched_fragments": [best_fragment] if best_fragment else [],
                    "primary_field": best_field,
                    "primary_fragment": best_fragment,
                    "row_data": self._serialize_row_payload(collection, row),
                }
            )

        scored_rows.sort(key=lambda item: item["score"], reverse=True)
        return scored_rows[:limit]

    async def _fetch_full_rows(
        self,
        session: Any,
        collection: Any,
        row_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch full row data from the dynamic SQL table."""
        if not row_ids or not collection.table_name:
            return {}

        from sqlalchemy import text as sa_text

        placeholders = ", ".join([f":rid_{i}" for i in range(len(row_ids))])
        params = {f"rid_{i}": rid for i, rid in enumerate(row_ids)}

        q = sa_text(
            f"SELECT * FROM {collection.table_name} WHERE id::text IN ({placeholders})"
        )
        rows = (await session.execute(q, params)).mappings().all()

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            rid = str(row.get("id", ""))
            result[rid] = self._serialize_row_payload(collection, dict(row))
        return result

    def _serialize_row_payload(
        self,
        collection: Any,
        row: Dict[str, Any],
    ) -> Dict[str, Any]:
        row_data: Dict[str, Any] = {}
        for field_def in collection.fields:
            fname = field_def["name"]
            ftype = field_def["data_type"]
            val = row.get(fname)
            if val is None:
                continue
            if ftype == "file":
                continue
            row_data[fname] = self._serialize_scalar(val)
        return row_data

    @staticmethod
    def _serialize_scalar(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, str) and len(value) > 500:
            return value[:497] + "..."
        if isinstance(value, list):
            return [CollectionTextSearchTool._serialize_scalar(item) for item in value]
        if isinstance(value, tuple):
            return [CollectionTextSearchTool._serialize_scalar(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): CollectionTextSearchTool._serialize_scalar(item)
                for key, item in value.items()
            }
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return str(value)
