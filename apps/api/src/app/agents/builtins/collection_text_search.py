"""
Collection Text Search Tool — векторный поиск по table-коллекциям.

Ищет в Qdrant-коллекции, привязанной к конкретной table-коллекции
(collection.qdrant_collection_name). Возвращает найденные строки
с полными данными из SQL-таблицы.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, ClassVar, Dict, List, Optional

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "Slug of the table collection to search in",
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
    Векторный (семантический) поиск по table-коллекциям.

    Table-коллекции могут иметь text-поля с `used_in_retrieval=true`.
    Эти поля векторизуются и хранятся в отдельной Qdrant-коллекции.

    Результаты обогащаются полными данными из SQL-таблицы.
    """

    tool_slug: ClassVar[str] = "collection.text_search"
    domains: ClassVar[list] = ["collection.table"]
    name: ClassVar[str] = "Collection Text Search"
    description: ClassVar[str] = (
        "Semantic search within a table collection that has retrieval-enabled text fields. "
        "Finds rows with semantically similar text using vector similarity. "
        "Returns matched text, relevance score, and full row data."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Vector search in table collections with Qdrant + SQL row enrichment",
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
        from app.services.collection_service import CollectionService

        log = ctx.tool_logger("collection.text_search")

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
            tenant_id = str(ctx.tenant_id)
            tenant_uuid = uuid.UUID(tenant_id)

            session_factory = get_session_factory()
            async with session_factory() as session:
                # 1. Resolve collection
                service = CollectionService(session)
                collection = await service.get_by_slug(tenant_uuid, collection_slug)
                if not collection:
                    log.error("Collection not found", collection=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
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

                # 2. Resolve embedding model and embed query
                vector_store = QdrantVectorStore()
                embedding_alias = await self._resolve_embedding_alias(
                    vector_store, collection.qdrant_collection_name
                )
                if not embedding_alias:
                    log.error("No embedding models")
                    return ToolResult.fail(
                        "Cannot determine embedding model for this collection.",
                        logs=log.entries_dict(),
                    )

                await EmbeddingServiceFactory.ensure_model_registered_async(session, embedding_alias)
                embedding_service = EmbeddingServiceFactory.get_service(embedding_alias)
                query_embedding = await asyncio.to_thread(
                    embedding_service.embed_texts, [query]
                )
                query_embedding = query_embedding[0]

                # 3. Build Qdrant filter
                qdrant_filter_must: List[tuple] = []
                if field_name:
                    qdrant_filter_must.append(("field_name", field_name))
                if payload_filters:
                    for fkey, fval in payload_filters.items():
                        qdrant_filter_must.append((fkey, fval))

                search_filter = {"must": qdrant_filter_must} if qdrant_filter_must else None

                # 4. Search in Qdrant
                exists = await vector_store.collection_exists(collection.qdrant_collection_name)
                if not exists:
                    log.warning("Qdrant collection does not exist yet")
                    return ToolResult.ok(
                        data={
                            "hits": [],
                            "total": 0,
                            "collection": collection.name,
                            "vector_fields": vector_fields,
                        },
                        message="Collection exists but has not been vectorized yet.",
                        logs=log.entries_dict(),
                    )

                results = await vector_store.search(
                    collection=collection.qdrant_collection_name,
                    query=query_embedding,
                    top_k=limit * 2,
                    filter=search_filter,
                )

                if not results:
                    log.info("No results found")
                    return ToolResult.ok(
                        data={
                            "hits": [],
                            "total": 0,
                            "collection": collection.name,
                            "vector_fields": vector_fields,
                        },
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
                        "collection": collection.name,
                        "vector_fields": vector_fields,
                    },
                    logs=log.entries_dict(),
                )

        except Exception as e:
            logger.error(f"Collection text search failed: {e}", exc_info=True)
            log.error("Search failed", error=str(e))
            return ToolResult.fail(f"Search failed: {str(e)}", logs=log.entries_dict())

    async def _resolve_embedding_alias(
        self, vector_store: Any, qdrant_collection_name: str
    ) -> Optional[str]:
        """
        Resolve embedding model alias by sampling a point from the Qdrant collection.
        Falls back to default embedding model from DB if no points exist.
        """
        try:
            client = vector_store._client
            scroll_result = await client.scroll(
                collection_name=qdrant_collection_name,
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            points = scroll_result[0] if scroll_result else []
            if points:
                alias = points[0].payload.get("embed_model_alias")
                if alias:
                    return alias
        except Exception as e:
            logger.warning(f"Failed to sample point from {qdrant_collection_name}: {e}")

        # Fallback: get default embedding model from DB
        try:
            from sqlalchemy import select
            from app.core.db import get_session_factory
            from app.models.model_registry import ModelRegistry, ModelType, ModelStatus

            session_factory = get_session_factory()
            async with session_factory() as session:
                result = await session.execute(
                    select(ModelRegistry.alias).where(
                        ModelRegistry.type == ModelType.EMBEDDING,
                        ModelRegistry.enabled == True,
                        ModelRegistry.status == ModelStatus.AVAILABLE,
                    ).limit(1)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Failed to get default embedding model: {e}")
            return None

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
            row_data: Dict[str, Any] = {}
            for field_def in collection.fields:
                fname = field_def["name"]
                ftype = field_def["data_type"]
                val = row.get(fname)
                if val is None:
                    continue
                if ftype == "file":
                    continue
                if isinstance(val, uuid.UUID):
                    val = str(val)
                if isinstance(val, str) and len(val) > 500:
                    val = val[:497] + "..."
                row_data[fname] = val
            result[rid] = row_data
        return result
