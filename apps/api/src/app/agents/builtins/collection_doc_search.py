"""
Collection Document Search Tool — векторный поиск по document-коллекциям.

Ищет в dedicated Qdrant-коллекции (collection.qdrant_collection_name),
которая создаётся при создании document-collection (coll_{tenant_short}_{slug}).
Обогащает результаты метаданными из динамической таблицы и именами документов.
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
            "description": "Slug of the document collection to search in",
        },
        "query": {
            "type": "string",
            "description": "Natural language search query",
        },
        "k": {
            "type": "integer",
            "description": "Number of results to return (default: 5, max: 20)",
            "default": 5,
            "minimum": 1,
            "maximum": 20,
        },
        "filters": {
            "type": "object",
            "description": "Optional collection field filters (eq semantics, list means IN).",
            "additionalProperties": True,
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
                    "text": {"type": "string"},
                    "source_name": {"type": "string"},
                    "score": {"type": "number"},
                    "page": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
            },
        },
        "total": {"type": "integer"},
        "collection": {"type": "string"},
        "applied_filters": {"type": "object"},
    },
}


@register_tool
class CollectionDocSearchTool(VersionedTool):
    """
    Векторный поиск по document-коллекциям.

    Document-коллекции хранят файлы, прошедшие RAG pipeline.
    Вектора лежат в dedicated Qdrant collection, привязанной к самой
    document-коллекции (`collection.qdrant_collection_name`).

    Результаты обогащаются:
    - именами документов-источников
    - метаданными из динамической таблицы коллекции (title, source и т.д.)
    """

    tool_slug: ClassVar[str] = "collection.doc_search"
    domains: ClassVar[list] = ["collection.document"]
    name: ClassVar[str] = "Collection Document Search"
    description: ClassVar[str] = (
        "Semantic search within a document collection. "
        "Finds relevant text fragments from uploaded documents "
        "using vector similarity. Returns text, source document name, "
        "relevance score, and collection metadata."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Vector search in dedicated Qdrant collection for document collections",
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

        log = ctx.tool_logger("collection.doc_search")

        collection_slug = args["collection_slug"]
        query = args["query"]
        try:
            k = min(int(args.get("k", 5)), 20)
        except (TypeError, ValueError):
            k = 5
        filters = args.get("filters", {}) or {}

        log.info(
            "Starting document collection search",
            collection=collection_slug,
            query=query[:100],
            k=k,
        )

        try:
            tenant_id = str(ctx.tenant_id)
            tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id

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

                if collection.collection_type != "document":
                    log.error("Not a document collection", type=collection.collection_type)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' is not a document collection "
                        f"(type={collection.collection_type}). Use collection.text_search for table collections.",
                        logs=log.entries_dict(),
                    )

                if not collection.qdrant_collection_name:
                    log.error("No Qdrant collection configured")
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' has no Qdrant collection configured.",
                        logs=log.entries_dict(),
                    )
                validation_error = self._validate_filters(collection, filters)
                if validation_error:
                    return ToolResult.fail(validation_error, logs=log.entries_dict())

                # 2. Check Qdrant collection exists
                vector_store = QdrantVectorStore()
                exists = await vector_store.collection_exists(collection.qdrant_collection_name)
                if not exists:
                    log.warning("Qdrant collection does not exist yet")
                    return ToolResult.ok(
                        data={
                            "hits": [],
                            "total": 0,
                            "collection": collection.name,
                            "applied_filters": filters or {},
                        },
                        message="Collection exists but has not been indexed yet.",
                        logs=log.entries_dict(),
                    )

                # 3. Resolve embedding model from Qdrant points metadata
                embedding_alias = await self._resolve_embedding_alias(
                    vector_store, collection.qdrant_collection_name
                )
                if not embedding_alias:
                    log.error("Cannot determine embedding model")
                    return ToolResult.fail(
                        "Cannot determine embedding model for this collection.",
                        logs=log.entries_dict(),
                    )

                # 4. Embed query
                await EmbeddingServiceFactory.ensure_model_registered_async(session, embedding_alias)
                embedding_service = EmbeddingServiceFactory.get_service(embedding_alias)
                query_embedding = await asyncio.to_thread(
                    embedding_service.embed_texts, [query]
                )
                query_embedding = query_embedding[0]

                row_ids: list[str] | None = None
                if filters:
                    row_ids = await self._resolve_filtered_row_ids(session, collection, filters)
                    if not row_ids:
                        return ToolResult.ok(
                            data={"hits": [], "total": 0, "collection": collection.name, "applied_filters": filters},
                            logs=log.entries_dict(),
                        )
                    if len(row_ids) > 2000:
                        return ToolResult.fail(
                            "Filters are too broad. Please narrow filters to 2000 rows or fewer.",
                            logs=log.entries_dict(),
                        )

                # 5. Search in dedicated Qdrant collection (no collection_id filter needed)
                results = await vector_store.search(
                    collection=collection.qdrant_collection_name,
                    query=query_embedding,
                    top_k=k * 2,
                    filter={"row_id": row_ids} if row_ids is not None else None,
                )

                if not results:
                    log.info("No results found")
                    return ToolResult.ok(
                        data={"hits": [], "total": 0, "collection": collection.name, "applied_filters": filters or {}},
                        logs=log.entries_dict(),
                    )

                # 6. Deduplicate by chunk_id, keep best score
                seen: Dict[str, Dict[str, Any]] = {}
                for hit in results:
                    chunk_id = hit.get("payload", {}).get("chunk_id", hit.get("id"))
                    if chunk_id not in seen or hit["score"] > seen[chunk_id]["score"]:
                        seen[chunk_id] = hit

                sorted_hits = sorted(seen.values(), key=lambda h: h["score"], reverse=True)[:k]

                # 6.1 Rerank results (required for document collections)
                rerank_inputs = [
                    str(hit.get("payload", {}).get("text") or "")
                    for hit in sorted_hits
                ]
                try:
                    reranked = await rerank_scores(
                        session=session,
                        query=query,
                        documents=rerank_inputs,
                        top_k=len(rerank_inputs),
                    )
                    sorted_hits = apply_rerank_to_items(sorted_hits, reranked, score_field="score")
                except RerankClientError as exc:
                    log.error("Rerank required but unavailable", error=str(exc))
                    return ToolResult.fail(
                        "Document search requires rerank, but rerank service is unavailable.",
                        logs=log.entries_dict(),
                    )

                # 7. Enrich with source names
                source_ids = list(
                    {h["payload"].get("source_id") for h in sorted_hits if h.get("payload", {}).get("source_id")}
                )
                source_names = await self._get_source_names(session, source_ids)

                # 8. Enrich with collection metadata from dynamic table
                row_ids = list(
                    {h["payload"].get("row_id") for h in sorted_hits if h.get("payload", {}).get("row_id")}
                )
                row_meta = await self._get_row_metadata(session, collection, row_ids)

                # 9. Format response
                hits = []
                sources = []
                for hit in sorted_hits:
                    payload = hit.get("payload", {})
                    source_id = payload.get("source_id", "")
                    row_id = payload.get("row_id")

                    text = payload.get("text", "").strip()
                    if len(text) > 500:
                        text = text[:497] + "..."

                    source_name = source_names.get(source_id, "Без названия")
                    meta = row_meta.get(row_id, {}) if row_id else {}

                    hit_entry = {
                        "text": text,
                        "source_name": source_name,
                        "score": round(hit["score"], 3),
                        "page": payload.get("page", 0),
                    }
                    if meta:
                        hit_entry["metadata"] = meta

                    hits.append(hit_entry)

                    sources.append({
                        "source_id": source_id,
                        "source_name": source_name,
                        "chunk_id": payload.get("chunk_id"),
                        "text": text[:200],
                        "page": payload.get("page", 0),
                        "score": round(hit["score"], 3),
                        "meta": meta,
                    })

                log.info(
                    "Search completed",
                    hits_count=len(hits),
                    top_score=round(sorted_hits[0]["score"], 3) if sorted_hits else 0,
                )

                return ToolResult.ok(
                    data={
                        "hits": hits,
                        "total": len(hits),
                        "collection": collection.name,
                        "applied_filters": filters or {},
                    },
                    sources=sources,
                    logs=log.entries_dict(),
                )

        except Exception as e:
            logger.error(f"Collection doc search failed: {e}", exc_info=True)
            log.error("Search failed", error=str(e))
            return ToolResult.fail(f"Search failed: {str(e)}", logs=log.entries_dict())

    async def _resolve_embedding_alias(
        self, vector_store: Any, qdrant_collection_name: str
    ) -> Optional[str]:
        """
        Resolve embedding model alias by sampling a point from the Qdrant collection.
        Falls back to default embedding model from DB if no points exist.
        """
        # Use Qdrant scroll to get a sample point
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
                row = result.scalar_one_or_none()
                return row
        except Exception as e:
            logger.warning(f"Failed to get default embedding model: {e}")
            return None

    async def _get_source_names(
        self, session: Any, source_ids: List[str]
    ) -> Dict[str, str]:
        """Batch-fetch document names by source_id."""
        if not source_ids:
            return {}
        from sqlalchemy import select
        from app.models.rag import RAGDocument

        result = await session.execute(
            select(RAGDocument.id, RAGDocument.name, RAGDocument.title, RAGDocument.filename).where(
                RAGDocument.id.in_([uuid.UUID(sid) for sid in source_ids])
            )
        )
        return {
            str(row.id): (row.name or row.title or row.filename or "Без названия")
            for row in result.fetchall()
        }

    async def _get_row_metadata(
        self, session: Any, collection: Any, row_ids: List[str]
    ) -> Dict[str, Dict[str, str]]:
        """Fetch metadata from the dynamic table for given row_ids."""
        if not row_ids or not collection.table_name or not collection.fields:
            return {}

        non_file_fields = [
            f["name"]
            for f in collection.fields
            if f.get("data_type") != "file"
        ]
        if not non_file_fields:
            return {}

        from sqlalchemy import text as sa_text

        cols = ", ".join(non_file_fields)
        placeholders = ", ".join([f":rid_{i}" for i in range(len(row_ids))])
        params = {f"rid_{i}": rid for i, rid in enumerate(row_ids)}

        q = sa_text(
            f"SELECT id::text, {cols} FROM {collection.table_name} "
            f"WHERE id::text IN ({placeholders})"
        )
        rows = (await session.execute(q, params)).mappings().all()

        result: Dict[str, Dict[str, str]] = {}
        for row in rows:
            rid = row["id"]
            meta: Dict[str, str] = {}
            for fname in non_file_fields:
                val = row.get(fname)
                if val is not None:
                    meta[fname] = str(val) if not isinstance(val, str) else val
            result[rid] = meta
        return result

    def _validate_filters(self, collection: Any, filters: Dict[str, Any]) -> Optional[str]:
        if not filters:
            return None
        field_map = {
            f.get("name"): f
            for f in (collection.fields or [])
            if isinstance(f, dict)
        }
        for key in filters.keys():
            field = field_map.get(key)
            if not field or not field.get("filterable", False):
                return f"Unknown or non-filterable field '{key}' in filters"
        for key, value in filters.items():
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, (dict, list, tuple, set)):
                    return f"Unsupported filter value for '{key}'"
        return None

    async def _resolve_filtered_row_ids(self, session: Any, collection: Any, filters: Dict[str, Any]) -> list[str]:
        if not collection.table_name:
            return []
        from sqlalchemy import text as sa_text

        where_parts: list[str] = []
        params: Dict[str, Any] = {}
        idx = 0
        for field, value in filters.items():
            if isinstance(value, list):
                if not value:
                    return []
                placeholders = []
                for item in value:
                    p = f"p{idx}"
                    idx += 1
                    params[p] = item
                    placeholders.append(f":{p}")
                where_parts.append(f"{field} IN ({', '.join(placeholders)})")
            else:
                p = f"p{idx}"
                idx += 1
                params[p] = value
                where_parts.append(f"{field} = :{p}")
        where_sql = " AND ".join(where_parts) if where_parts else "TRUE"
        q = sa_text(f"SELECT id::text FROM {collection.table_name} WHERE {where_sql} LIMIT 2001")
        rows = (await session.execute(q, params)).all()
        return [str(row[0]) for row in rows if row and row[0]]
